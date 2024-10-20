import contextlib
import logging
import mmap
import os
from collections.abc import Callable, Sequence
from io import BufferedReader
from pathlib import Path

import watchfiles

from logcafe.schemas import LogWatchConfig

logging.basicConfig(
    filename="output.log",
    format=r"%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
)


class LogFilter(watchfiles.DefaultFilter):
    __slots__ = ("allowed_prefix",)

    def __init__(self, *args, allowed_prefix: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.allowed_prefix = allowed_prefix

    def __call__(self, change: watchfiles.Change, path: str) -> bool:
        return os.path.split(path)[1].startswith(self.allowed_prefix) and super().__call__(
            change, path
        )


async def watch_log_change(  # noqa: C901
    watch_config: LogWatchConfig,
    callback: Callable[[Sequence[str]], object],
) -> None:
    log_prefix = watch_config.log_prefix
    watch_dir = Path(watch_config.directory).resolve()
    last_inode, last_offset = await pre_watch(watch_config, callback)
    batch: list[str] = []

    async for _ in watchfiles.awatch(
        watch_dir,
        watch_filter=LogFilter(allowed_prefix=log_prefix),
        recursive=False,
    ):
        with contextlib.ExitStack() as stack:
            files: dict[Path, BufferedReader] = {}
            found = False
            prev_inode: int = 0
            for p in sorted(
                watch_dir.glob(rf"{log_prefix}*"),
                key=lambda _p: 0 if _p.name == log_prefix else int(_p.name.rpartition(".")[2]),
                # sorting: this assumes files are named e.g. x.log, x.log.1, x.log.2 etc.
                # which is the default in many rotating loggers
                # provide strategy customization if needed
            ):
                # we want to open every file that we need to read
                # so that if a rotation occurs later,
                # we do not lose track and end up missing a file or reading a file twice
                stat = p.stat()
                if not p.is_file() or stat.st_size == 0:
                    continue
                if stat.st_ino == last_inode:
                    found = True
                if stat.st_ino == prev_inode:
                    # handle rotations during this for loop?
                    continue
                files[p] = stack.enter_context(open(p, "rb"))
                if found:
                    break
                prev_inode = stat.st_ino
            if not found:
                last_offset = 0

            for idx, (path, f) in enumerate(reversed(files.items())):
                with contextlib.closing(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)) as m:
                    if idx == 0:
                        m.seek(last_offset)
                    while line := m.readline():
                        batch.append(line.decode("utf-8"))
                    last_offset = m.tell()
                    last_inode = path.stat().st_ino

            try:
                callback(batch)
            finally:
                batch.clear()

            # TODO: An exception while reading logs shouldn't brick the entire app
            # However, suppressing exceptions entirely is not ideal, so
            # instead of suppressing exceptions, have a separate callback to
            # display toast notifications


async def pre_watch(
    watch_config: LogWatchConfig,
    callback: Callable[[Sequence[str]], object],
) -> tuple[int, int]:
    log_prefix = watch_config.log_prefix
    watch_dir = Path(watch_config.directory).resolve()
    batch: list[str] = []
    last_inode: int = 0
    last_offset: int = 0

    with contextlib.suppress(Exception):
        if existing_files := sorted(
            filter(
                lambda x: x.is_file() and x.stat().st_size > 0,
                watch_dir.glob(rf"{log_prefix}*"),
            ),
            key=lambda y: y.stat().st_mtime,
            reverse=True,
        ):
            with open(path := existing_files[0], "rb") as f:
                with contextlib.closing(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)) as m:
                    while line := m.readline():
                        batch.append(line.decode("utf-8"))
                    callback(batch)
                    last_inode = path.stat().st_ino
                    last_offset = m.tell()
    return last_inode, last_offset

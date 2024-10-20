import functools
from pathlib import Path

import msgspec
import rtoml

from logcafe.schemas import LogWatchConfig

APP_DIR = Path(__file__).resolve().parent
APP_NAME = APP_DIR.name

TCSS_DIR = APP_DIR / "tcss"
APP_TCSS = TCSS_DIR / "app.tcss"
assert APP_TCSS.is_file()


@functools.cache
def load_watchers_config() -> list[LogWatchConfig]:
    d = rtoml.load(Path.cwd() / "logcafe.toml")
    if (objs := d.get("watch", None)) is None:
        raise RuntimeError("No watchers defined")

    result = []
    for obj in objs.values():
        result.append(msgspec.convert(obj, LogWatchConfig))

    return result

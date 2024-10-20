import asyncio
import contextlib
import functools
import sys
from collections.abc import Sequence

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, RichLog, Static, TabbedContent, TabPane

from logcafe.config import APP_TCSS, load_watchers_config
from logcafe.schemas import LogWatchConfig
from logcafe.utils import curr_time
from logcafe.watch import watch_log_change


class LogArea(Static):
    def compose(self) -> ComposeResult:
        with TabbedContent():
            for config in load_watchers_config():
                with TabPane(config.tab_title, id=config.tab_id):
                    yield RichLog(id=config.logger_id)


class LogCafeApp(App):
    CSS_PATH = APP_TCSS

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Footer()
        yield LogArea()
        yield DataTable(id="stats")

    async def on_mount(self) -> None:
        stats_table = self.query_one("#stats", DataTable)
        for col in [
            "name",
            "lines",
            "warnings",
            "errors",
            "last_updated",
        ]:
            stats_table.add_column(col, key=col)

        self.watchers: list[asyncio.Task] = []
        for config in load_watchers_config():
            stats_table.add_row(
                config.norm_name,
                "0",
                "0",
                "0",
                curr_time(),
                key=config.norm_name,
            )
            watcher = asyncio.create_task(
                watch_log_change(
                    watch_config=config,
                    callback=functools.partial(
                        self.message_callback,
                        config=config,
                        destination=self.query_one(f"#{config.logger_id}", RichLog),
                        stats_table=stats_table,
                    ),
                )
            )
            self.watchers.append(watcher)

    def message_callback(
        self,
        messages: Sequence[str],
        *,
        config: LogWatchConfig,
        destination: RichLog,
        stats_table: DataTable,
    ) -> None:
        warnings = 0
        errors = 0
        for message in messages:
            destination.write(message)
            with contextlib.suppress(IndexError):
                level = message.split()[config.level_field].lower()
                if "warn" in level:
                    warnings += 1
                elif "error" in level or "fatal" in level or "critical" in level:
                    errors += 1
        if errors:
            self.notify(f"Errors in {config.tab_title}", severity="error", timeout=5)
        elif warnings:
            self.notify(f"Warnings in {config.tab_title}", severity="warning", timeout=5)

        config.messages += len(messages)
        config.warnings += warnings
        config.errors += errors
        stats_table.update_cell(config.norm_name, "lines", str(config.messages))
        stats_table.update_cell(config.norm_name, "warnings", str(config.warnings))
        stats_table.update_cell(config.norm_name, "errors", str(config.errors))
        stats_table.update_cell(config.norm_name, "last_updated", curr_time())

    async def on_unmount(self) -> None:
        for watcher in self.watchers:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher


def main() -> None:
    app = LogCafeApp()
    app.run()


if __name__ == "__main__":
    sys.exit(main())

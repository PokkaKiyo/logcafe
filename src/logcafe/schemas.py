from msgspec import Struct, field


class LogWatchConfig(Struct, kw_only=True):
    tab_title: str
    directory: str
    log_prefix: str
    level_field: int
    norm_name: str = field(default="")
    tab_id: str = field(default="")
    logger_id: str = field(default="")
    messages: int = 0
    warnings: int = 0
    errors: int = 0

    def __post_init__(self) -> None:
        self.norm_name = self.norm_name or "".join(self.tab_title.lower().split())
        self.tab_id = self.tab_id or f"{self.norm_name}_tab"
        self.logger_id = self.logger_id or f"{self.norm_name}_logger"

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    "venv",
    ".venv",
    "dist",
    "build",
    "target",
    ".idea",
    ".vscode",
}


@dataclass
class AppConfig:
    root: Path
    host: str = "127.0.0.1"
    port: int = 9999
    token: str | None = None
    readonly: bool = False
    show_hidden: bool = False
    max_upload_mb: int = 512
    max_preview_mb: int = 5
    max_search_results: int = 500
    exclude_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDE_DIRS))
    allow_no_token_on_lan: bool = False

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()
        if not self.root.exists():
            raise ValueError(f"Root does not exist: {self.root}")
        if not self.root.is_dir():
            raise ValueError(f"Root is not a directory: {self.root}")
        if self.max_upload_mb < 1:
            raise ValueError("max_upload_mb must be at least 1")
        if self.max_preview_mb < 1:
            raise ValueError("max_preview_mb must be at least 1")
        if self.max_search_results < 1:
            raise ValueError("max_search_results must be at least 1")
        self.exclude_dirs = {name.strip() for name in self.exclude_dirs if name.strip()}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_preview_bytes(self) -> int:
        return self.max_preview_mb * 1024 * 1024

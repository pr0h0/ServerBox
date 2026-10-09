from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from .config import AppConfig
from .fs import FileItem, build_file_item
from .security import is_inside_root


def search_files(
    config: AppConfig, query: str, start_dir: Path, should_stop: Callable[[], bool] | None = None
) -> list[FileItem]:
    """Recursive name search. Stops early at max results or once `should_stop()` returns True."""
    needle = query.casefold().strip()
    if not needle:
        return []

    results: list[FileItem] = []
    start_dir = start_dir.resolve(strict=False)
    if not is_inside_root(config.root, start_dir) or not start_dir.is_dir():
        return results

    def walk(directory: Path) -> None:
        if len(results) >= config.max_search_results or (should_stop and should_stop()):
            return
        try:
            with os.scandir(directory) as entries:
                sorted_entries = sorted(entries, key=lambda entry: entry.name.casefold())
        except OSError:
            return

        for entry in sorted_entries:
            if len(results) >= config.max_search_results or (should_stop and should_stop()):
                return
            if not config.show_hidden and entry.name.startswith("."):
                continue
            if entry.name in config.exclude_dirs and entry.is_dir(follow_symlinks=False):
                continue

            path = Path(entry.path)
            try:
                if entry.is_symlink():
                    resolved = path.resolve(strict=True)
                    if not is_inside_root(config.root, resolved):
                        continue
                else:
                    resolved = path.resolve(strict=False)
                    if not is_inside_root(config.root, resolved):
                        continue
            except OSError:
                continue

            if needle in entry.name.casefold():
                results.append(build_file_item(config, path))
                if len(results) >= config.max_search_results:
                    return

            if entry.is_dir(follow_symlinks=False):
                walk(path)

    walk(start_dir)
    return results

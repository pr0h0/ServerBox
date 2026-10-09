from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import HTTPException


# Finder's default color tags.
TAG_COLORS = ("red", "orange", "yellow", "green", "blue", "purple", "gray")
TAGS_FILENAME = ".servebox-tags.json"


class TagStore:
    """Tags keyed by root-relative path, persisted as JSON in the served root so they travel with it."""

    # ponytail: whole file rewritten on every change; fine for thousands of tags, use sqlite beyond that.
    def __init__(self, root: Path) -> None:
        self.path = root / TAGS_FILENAME
        self.data: dict[str, list[str]] = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if isinstance(key, str) and isinstance(value, list):
                    tags = [tag for tag in TAG_COLORS if tag in value]
                    if tags:
                        self.data[key] = tags

    def _save(self) -> None:
        tmp = self.path.with_name(TAGS_FILENAME + ".tmp")
        try:
            tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not save tags: {exc}") from exc

    def get(self, rel: str) -> list[str]:
        return list(self.data.get(rel, []))

    def set(self, rel: str, tags: list[str]) -> list[str]:
        if not rel:
            raise HTTPException(status_code=400, detail="Cannot tag the root directory")
        unknown = set(tags) - set(TAG_COLORS)
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown tag: {sorted(unknown)[0]}")
        clean = [tag for tag in TAG_COLORS if tag in tags]
        if clean:
            self.data[rel] = clean
        else:
            self.data.pop(rel, None)
        self._save()
        return clean

    def move(self, old: str, new: str | None) -> None:
        """Re-key `old` and everything below it to `new`; `new=None` drops them."""
        affected = [key for key in self.data if key == old or key.startswith(old + "/")]
        for key in affected:
            tags = self.data.pop(key)
            if new is not None:
                self.data[new + key[len(old):]] = tags
        if affected:
            self._save()

    def with_tag(self, tag: str) -> list[str]:
        return sorted(key for key, tags in self.data.items() if tag in tags)

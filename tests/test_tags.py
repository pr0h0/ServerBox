from pathlib import Path

import pytest
from fastapi import HTTPException

from servebox.tags import TagStore


def test_tags_persist_and_follow_rename_and_delete(tmp_path: Path) -> None:
    store = TagStore(tmp_path)
    store.set("docs", ["blue"])
    store.set("docs/a.txt", ["red", "green", "red"])

    store.move("docs", "papers")
    reloaded = TagStore(tmp_path)

    assert reloaded.get("papers/a.txt") == ["red", "green"]  # canonical order, deduped
    assert reloaded.with_tag("blue") == ["papers"]
    reloaded.move("papers", None)
    assert reloaded.data == {}


def test_tags_reject_unknown_colors(tmp_path: Path) -> None:
    with pytest.raises(HTTPException):
        TagStore(tmp_path).set("a.txt", ["pink"])


def test_move_does_not_touch_sibling_prefixes(tmp_path: Path) -> None:
    store = TagStore(tmp_path)
    store.set("doc", ["red"])
    store.set("docs", ["blue"])

    store.move("doc", "x")

    assert store.data == {"x": ["red"], "docs": ["blue"]}

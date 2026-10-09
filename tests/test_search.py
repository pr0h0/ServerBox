from pathlib import Path

from servebox.config import AppConfig
from servebox.search import search_files


def test_search_respects_max_results(tmp_path: Path) -> None:
    for index in range(10):
        (tmp_path / f"match-{index}.txt").write_text("x")
    config = AppConfig(root=tmp_path, max_search_results=3)

    results = search_files(config, "match", tmp_path)

    assert len(results) == 3


def test_search_skips_excluded_directories(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "needle.txt").write_text("visible")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "needle.txt").write_text("hidden")
    config = AppConfig(root=tmp_path, exclude_dirs={".git"})

    results = search_files(config, "needle", tmp_path)

    assert [result.relative_path for result in results] == ["keep/needle.txt"]


def test_search_stops_when_asked(tmp_path: Path) -> None:
    (tmp_path / "match.txt").write_text("x")
    config = AppConfig(root=tmp_path)

    assert search_files(config, "match", tmp_path, should_stop=lambda: True) == []

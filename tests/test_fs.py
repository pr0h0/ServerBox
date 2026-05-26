from pathlib import Path

from servebox.config import AppConfig
from servebox.fs import list_directory, relative_path


def test_list_directory_hides_hidden_files_by_default(tmp_path: Path) -> None:
    (tmp_path / ".secret").write_text("hidden")
    (tmp_path / "visible.txt").write_text("visible")
    config = AppConfig(root=tmp_path, show_hidden=False)

    items = list_directory(config, tmp_path)

    assert [item.name for item in items] == ["visible.txt"]


def test_list_directory_places_folders_before_files(tmp_path: Path) -> None:
    (tmp_path / "z-file.txt").write_text("file")
    (tmp_path / "a-folder").mkdir()
    config = AppConfig(root=tmp_path)

    items = list_directory(config, tmp_path)

    assert [item.name for item in items] == ["a-folder", "z-file.txt"]


def test_relative_path_serializes_root_as_empty_path(tmp_path: Path) -> None:
    config = AppConfig(root=tmp_path)

    assert relative_path(config, tmp_path) == ""

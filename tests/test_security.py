from pathlib import Path

import pytest
from fastapi import HTTPException

from servebox.config import AppConfig
from servebox.fs import auto_rename_target
from servebox.security import safe_resolve, validate_upload_filename


def make_config(root: Path) -> AppConfig:
    return AppConfig(root=root)


def test_safe_path_allows_root(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    assert safe_resolve(config, "") == tmp_path.resolve()


def test_safe_path_allows_nested_file_inside_root(tmp_path: Path) -> None:
    nested = tmp_path / "folder" / "file.txt"
    nested.parent.mkdir()
    nested.write_text("hello")
    config = make_config(tmp_path)

    assert safe_resolve(config, "folder/file.txt") == nested.resolve()


def test_safe_path_rejects_traversal_outside_root(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(HTTPException) as exc:
        safe_resolve(config, "../outside.txt")

    assert exc.value.status_code == 403


def test_safe_path_rejects_absolute_path(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(HTTPException) as exc:
        safe_resolve(config, "/etc/passwd")

    assert exc.value.status_code == 403


def test_safe_path_rejects_null_byte(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(HTTPException) as exc:
        safe_resolve(config, "bad\x00name")

    assert exc.value.status_code == 400


def test_symlink_pointing_outside_root_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-file.txt"
    outside.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    config = make_config(tmp_path)

    with pytest.raises(HTTPException) as exc:
        safe_resolve(config, "link.txt")

    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "filename",
    ["../evil.txt", "folder/file.txt", "folder\\file.txt", "bad\x00name", "", "."],
)
def test_upload_filename_validation_rejects_unsafe_names(filename: str) -> None:
    with pytest.raises(HTTPException):
        validate_upload_filename(filename)


def test_auto_rename_creates_numbered_target(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("one")
    (tmp_path / "file (1).txt").write_text("two")

    target = auto_rename_target(tmp_path, "file.txt")

    assert target == tmp_path / "file (2).txt"

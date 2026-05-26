from __future__ import annotations

import mimetypes
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from .config import AppConfig
from .security import is_inside_root, safe_child_path, validate_upload_filename


TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".html",
    ".css",
    ".scss",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".kt",
    ".swift",
    ".php",
    ".rb",
    ".sh",
    ".zsh",
    ".bash",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".env",
    ".sql",
    ".xml",
    ".csv",
    ".log",
}


@dataclass
class FileItem:
    name: str
    relative_path: str
    parent_path: str
    type: str
    size: int | None
    size_display: str
    modified: float | None
    modified_display: str
    mime_type: str | None
    preview_type: str
    previewable: bool
    is_symlink: bool
    target_outside: bool
    accessible: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def human_size(size: int | None) -> str:
    if size is None:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def relative_path(config: AppConfig, path: Path) -> str:
    try:
        rel = path.relative_to(config.root).as_posix()
        return "" if rel == "." else rel
    except ValueError:
        resolved = path.resolve(strict=False)
        if resolved == config.root:
            return ""
        rel = resolved.relative_to(config.root).as_posix()
        return "" if rel == "." else rel


def parent_relative_path(config: AppConfig, path: Path) -> str:
    rel = relative_path(config, path.parent)
    return "" if rel == "." else rel


def guess_mime_type(path: Path) -> str | None:
    mime_type, _encoding = mimetypes.guess_type(path.name)
    return mime_type


def preview_type_for(path: Path, mime_type: str | None, kind: str) -> str:
    if kind != "file":
        return "none"
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS or (mime_type and mime_type.startswith("text/")):
        return "text"
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type and mime_type.startswith("image/"):
        return "image"
    if mime_type and mime_type.startswith("audio/"):
        return "audio"
    if mime_type and mime_type.startswith("video/"):
        return "video"
    return "binary"


def _modified_display(timestamp: float | None) -> str:
    if timestamp is None:
        return "-"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _kind_from_stat(path: Path) -> str:
    if path.is_dir():
        return "folder"
    if path.is_file():
        return "file"
    return "other"


def build_file_item(config: AppConfig, path: Path) -> FileItem:
    is_symlink = path.is_symlink()
    target_outside = False
    accessible = True
    stat = None
    kind = "other"
    metadata_path = path

    try:
        lstat = path.lstat()
    except OSError:
        return FileItem(
            name=path.name,
            relative_path=relative_path(config, path),
            parent_path=parent_relative_path(config, path),
            type="other",
            size=None,
            size_display="-",
            modified=None,
            modified_display="-",
            mime_type=None,
            preview_type="none",
            previewable=False,
            is_symlink=is_symlink,
            target_outside=False,
            accessible=False,
        )

    if is_symlink:
        try:
            resolved = path.resolve(strict=True)
            target_outside = not is_inside_root(config.root, resolved)
            if target_outside:
                accessible = False
                stat = lstat
                kind = "symlink"
            else:
                stat = resolved.stat()
                metadata_path = resolved
                kind = _kind_from_stat(resolved)
        except OSError:
            accessible = False
            stat = lstat
            kind = "symlink"
    else:
        try:
            stat = path.stat()
            kind = _kind_from_stat(path)
        except OSError:
            accessible = False
            stat = lstat

    size = stat.st_size if stat and kind == "file" else None
    modified = stat.st_mtime if stat else None
    mime_type = guess_mime_type(metadata_path) if kind == "file" else None
    preview_type = preview_type_for(metadata_path, mime_type, kind) if accessible else "none"
    return FileItem(
        name=path.name,
        relative_path=relative_path(config, path),
        parent_path=parent_relative_path(config, path),
        type=kind,
        size=size,
        size_display=human_size(size),
        modified=modified,
        modified_display=_modified_display(modified),
        mime_type=mime_type,
        preview_type=preview_type,
        previewable=preview_type not in ("none", "binary"),
        is_symlink=is_symlink,
        target_outside=target_outside,
        accessible=accessible,
    )


def list_directory(config: AppConfig, directory: Path) -> list[FileItem]:
    if not directory.exists():
        raise HTTPException(status_code=404, detail="Directory not found")
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    try:
        children = list(directory.iterdir())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items: list[FileItem] = []
    for child in children:
        if not config.show_hidden and child.name.startswith("."):
            continue
        items.append(build_file_item(config, child))
    items.sort(key=lambda item: (0 if item.type == "folder" else 1, item.name.casefold()))
    return items


def child_directories(config: AppConfig, directory: Path) -> list[FileItem]:
    return [item for item in list_directory(config, directory) if item.type == "folder" and item.accessible]


def auto_rename_target(directory: Path, filename: str) -> Path:
    filename = validate_upload_filename(filename)
    requested = directory / filename
    if not requested.exists():
        return requested

    suffix = requested.suffix
    stem = requested.name[: -len(suffix)] if suffix else requested.name
    index = 1
    while True:
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def create_directory(config: AppConfig, directory: Path, name: str) -> FileItem:
    target = safe_child_path(config, directory, name)
    if target.exists():
        raise HTTPException(status_code=409, detail="A file or folder already exists with that name")
    try:
        target.mkdir()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return build_file_item(config, target)


def rename_path(config: AppConfig, path: Path, new_name: str) -> FileItem:
    if path == config.root:
        raise HTTPException(status_code=400, detail="Cannot rename the root directory")
    target = safe_child_path(config, path.parent, new_name)
    if target.exists():
        raise HTTPException(status_code=409, detail="A file or folder already exists with that name")
    try:
        path.rename(target)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return build_file_item(config, target)


def delete_path(config: AppConfig, path: Path) -> None:
    if path == config.root:
        raise HTTPException(status_code=400, detail="Cannot delete the root directory")
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def read_text_preview(path: Path, max_bytes: int) -> tuple[str, bool]:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            data = handle.read(max_bytes)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return data.decode("utf-8", errors="replace"), size > max_bytes

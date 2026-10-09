from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, Request

from .config import AppConfig


AUTH_COOKIE_NAME = "servebox_auth"
WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


def is_inside_root(root: Path, target: Path) -> bool:
    root = root.resolve()
    target = target.resolve(strict=False)
    return target == root or root in target.parents


def _path_parts(user_path: str | None) -> list[str]:
    if user_path is None or user_path == "":
        return []
    if not isinstance(user_path, str):
        raise HTTPException(status_code=400, detail="Path must be text")
    if "\x00" in user_path:
        raise HTTPException(status_code=400, detail="Path contains a null byte")
    if "\\" in user_path:
        raise HTTPException(status_code=400, detail="Backslashes are not valid path separators")
    if user_path.startswith("/") or PurePosixPath(user_path).is_absolute():
        raise HTTPException(status_code=403, detail="Absolute paths are not allowed")
    if WINDOWS_DRIVE_RE.match(user_path):
        raise HTTPException(status_code=403, detail="Absolute paths are not allowed")

    try:
        parts = [part for part in PurePosixPath(user_path).parts if part not in ("", ".")]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed path") from exc
    return parts


def safe_resolve(config: AppConfig, user_path: str | None, follow_final: bool = True) -> Path:
    """Resolve a user path inside the root.

    follow_final=False keeps a final symlink as-is (only its parent is resolved), so
    rename/move/delete act on the link itself instead of whatever it points to.
    """
    parts = _path_parts(user_path)
    if not follow_final and parts:
        parent = safe_resolve(config, "/".join(parts[:-1]))
        if parts[-1] == "..":
            raise HTTPException(status_code=403, detail="Path is outside the configured root")
        return parent / parts[-1]
    try:
        target = config.root.joinpath(*parts).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed path") from exc

    if not is_inside_root(config.root, target):
        raise HTTPException(status_code=403, detail="Path is outside the configured root")
    return target


def safe_child_path(config: AppConfig, directory: Path, filename: str) -> Path:
    validate_upload_filename(filename)
    try:
        target = (directory / filename).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed filename") from exc
    if not is_inside_root(config.root, target):
        raise HTTPException(status_code=403, detail="Target is outside the configured root")
    return target


def validate_upload_filename(filename: str | None) -> str:
    if filename is None:
        raise HTTPException(status_code=400, detail="Filename is required")
    if not isinstance(filename, str):
        raise HTTPException(status_code=400, detail="Filename must be text")
    if "\x00" in filename:
        raise HTTPException(status_code=400, detail="Filename contains a null byte")
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Filename must not contain path separators")
    if filename in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="Filename is not valid")
    if PurePosixPath(filename).is_absolute() or WINDOWS_DRIVE_RE.match(filename):
        raise HTTPException(status_code=403, detail="Absolute filenames are not allowed")
    if any(part in ("..", "") for part in PurePosixPath(filename).parts):
        raise HTTPException(status_code=400, detail="Filename must not contain traversal")
    return filename


def token_matches(expected: str, provided: str | None) -> bool:
    return bool(provided) and hmac.compare_digest(expected, str(provided))


def session_value(token: str) -> str:
    """Cookie value derived from the token, so the raw token never sits in the browser's cookie jar."""
    return hmac.new(token.encode("utf-8"), b"servebox-session", hashlib.sha256).hexdigest()


def request_has_valid_token(request: Request, config: AppConfig) -> bool:
    if not config.token:
        return True
    query_token = request.query_params.get("token")
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    return token_matches(config.token, query_token) or token_matches(session_value(config.token), cookie_token)


def safe_next(next_url: str | None) -> str:
    """Only allow same-site relative redirects after login (blocks //evil.com and /\\evil.com)."""
    if not next_url or not next_url.startswith("/") or next_url.startswith("//") or "\\" in next_url:
        return "/"
    return next_url

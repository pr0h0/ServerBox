from __future__ import annotations

import asyncio
import os
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import AppConfig
from .fs import (
    FileItem,
    auto_rename_target,
    build_file_item,
    child_directories,
    create_directory,
    delete_path,
    guess_mime_type,
    list_directory,
    move_path,
    read_text_preview,
    relative_path,
    rename_path,
)
from .search import search_files
from .security import (
    AUTH_COOKIE_NAME,
    is_inside_root,
    request_has_valid_token,
    safe_next,
    safe_resolve,
    session_value,
    token_matches,
    validate_upload_filename,
)
from .tags import TAG_COLORS, TagStore


PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))

SEARCH_TIME_LIMIT = 10  # seconds; a recursive walk of a huge tree returns partial results instead of running forever

PAGE_CSP = (
    "default-src 'self'; img-src 'self' data: blob:; media-src 'self'; frame-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
)
# User files may be HTML/SVG: sandbox them so they can't run script on our origin and call the API.
RAW_CSP = "sandbox; default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'"


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="ServeBox")
    app.state.config = config
    tag_store = TagStore(config.root)
    app.state.tags = tag_store
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @app.middleware("http")
    async def token_auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        if not config.token:
            return await call_next(request)
        path = request.url.path
        if path.startswith("/static/") or path == "/login":
            return await call_next(request)
        if request_has_valid_token(request, config):
            return await call_next(request)

        if path.startswith("/api/"):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        if path in {"/raw", "/download"}:
            return PlainTextResponse("Authentication required", status_code=401)

        next_url = path + (f"?{request.url.query}" if request.url.query else "")
        login_url = "/login?next=" + urllib.parse.quote(next_url, safe="")
        return RedirectResponse(login_url, status_code=303)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            # CSRF: reject state-changing requests coming from another site.
            origin = request.headers.get("origin")
            if origin and urllib.parse.urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "same-origin")
        headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        headers.setdefault("Content-Security-Policy", PAGE_CSP)
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):  # type: ignore[no-untyped-def]
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        if request.url.path in {"/raw", "/download"}:
            return PlainTextResponse(str(exc.detail), status_code=exc.status_code)
        return render_template(
            request,
            "error.html",
            status_code=exc.status_code,
            message=str(exc.detail),
        )

    def ensure_write_enabled() -> None:
        if config.readonly:
            raise HTTPException(status_code=403, detail="Readonly mode is enabled")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> RedirectResponse:
        return RedirectResponse("/browse", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request, next: str = "/") -> HTMLResponse:
        if not config.token:
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(request, "login.html", {"next": safe_next(next), "error": None})

    @app.post("/login", response_class=HTMLResponse)
    async def login(request: Request, token: str = Form(...), next: str = Form("/")) -> HTMLResponse:
        if not config.token:
            return RedirectResponse("/", status_code=303)
        if token_matches(config.token, token):
            response = RedirectResponse(safe_next(next), status_code=303)
            response.set_cookie(
                AUTH_COOKIE_NAME,
                session_value(config.token),
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 30,
            )
            return response
        await asyncio.sleep(1)  # slow down token guessing
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": safe_next(next), "error": "Invalid token"},
            status_code=401,
        )

    @app.post("/logout")
    async def logout() -> RedirectResponse:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(AUTH_COOKIE_NAME)
        return response

    @app.get("/browse", response_class=HTMLResponse)
    async def browse(
        request: Request, path: str = "", tag: str = "", q: str = "", scope: str = "root"
    ) -> HTMLResponse:
        directory = safe_resolve(config, path)
        if not directory.exists():
            raise HTTPException(status_code=404, detail="Directory not found")
        if not directory.is_dir():
            return RedirectResponse(f"/view?path={urllib.parse.quote(path)}", status_code=303)
        current_path = relative_path(config, directory)
        timed_out = False
        if tag:
            if tag not in TAG_COLORS:
                raise HTTPException(status_code=404, detail="Unknown tag")
            mode, items = "tag", tagged_items(tag)
        elif q.strip():
            if scope not in {"root", "current"}:
                raise HTTPException(status_code=400, detail="scope must be root or current")
            start = config.root if scope == "root" else directory
            items, timed_out = await run_search(q, start)
            mode = "search"
        else:
            mode, items = "folder", list_directory(config, directory)
        return render_template(
            request,
            "browse.html",
            current_path=current_path,
            items=with_tags(items),
            breadcrumbs=build_breadcrumbs(current_path),
            mode=mode,
            tag=tag,
            q=q,
            scope=scope,
            search_timed_out=timed_out,
            search_time_limit=SEARCH_TIME_LIMIT,
        )

    @app.get("/view", response_class=HTMLResponse)
    async def view_file(request: Request, path: str) -> HTMLResponse:
        target = safe_resolve(config, path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="File not found")
        if target.is_dir():
            return RedirectResponse(f"/browse?path={urllib.parse.quote(relative_path(config, target))}", status_code=303)
        item = with_tags([build_file_item(config, target)])[0]
        text_preview = None
        preview_truncated = False
        if item.preview_type == "text":
            text_preview, preview_truncated = read_text_preview(target, config.max_preview_bytes)
        return render_template(
            request,
            "view.html",
            current_path=item.parent_path,
            item=item,
            text_preview=text_preview,
            preview_truncated=preview_truncated,
            breadcrumbs=build_breadcrumbs(item.relative_path),
        )

    @app.get("/download")
    async def download(path: str) -> FileResponse:
        target = require_file(config, path)
        return FileResponse(target, filename=target.name, media_type="application/octet-stream")

    @app.get("/raw")
    async def raw(path: str) -> FileResponse:
        target = require_file(config, path)
        media_type = guess_mime_type(target) or "application/octet-stream"
        response = FileResponse(
            target,
            filename=target.name,
            media_type=media_type,
            content_disposition_type="inline",
        )
        # Browser PDF viewers refuse to run sandboxed; PDFs can't script our origin anyway.
        if media_type != "application/pdf":
            response.headers["Content-Security-Policy"] = RAW_CSP
        return response

    @app.get("/api/list")
    async def api_list(path: str = "") -> dict[str, Any]:
        directory = safe_resolve(config, path)
        items = [item.to_dict() for item in with_tags(list_directory(config, directory))]
        return {"path": relative_path(config, directory), "items": items}

    @app.get("/api/tree")
    async def api_tree(path: str = "") -> dict[str, Any]:
        directory = safe_resolve(config, path)
        items = [item.to_dict() for item in child_directories(config, directory)]
        return {"path": relative_path(config, directory), "items": items}

    @app.get("/api/search")
    async def api_search(q: str = "", scope: str = "root", path: str = "") -> dict[str, Any]:
        if scope not in {"root", "current"}:
            raise HTTPException(status_code=400, detail="scope must be root or current")
        start = config.root if scope == "root" else safe_resolve(config, path)
        items, timed_out = await run_search(q, start)
        results = [item.to_dict() for item in with_tags(items)]
        return {
            "query": q,
            "scope": scope,
            "results": results,
            "limit": config.max_search_results,
            "timed_out": timed_out,
        }

    @app.post("/api/upload")
    async def api_upload(path: str = "", files: list[UploadFile] = File(...)) -> dict[str, Any]:
        ensure_write_enabled()
        directory = safe_resolve(config, path)
        if not directory.is_dir():
            raise HTTPException(status_code=400, detail="Upload target is not a directory")
        uploaded = []
        for upload in files:
            filename = validate_upload_filename(upload.filename)
            target = auto_rename_target(directory, filename)
            if not is_inside_root(config.root, target):
                raise HTTPException(status_code=403, detail="Target is outside the configured root")
            total = 0
            try:
                # "xb" fails instead of following a symlink or clobbering a file created since the name check.
                async with aiofiles.open(target, "xb") as handle:
                    while chunk := await upload.read(1024 * 1024):
                        total += len(chunk)
                        if total > config.max_upload_bytes:
                            await handle.close()
                            target.unlink(missing_ok=True)
                            raise HTTPException(status_code=413, detail=f"{filename} exceeds upload limit")
                        await handle.write(chunk)
            except HTTPException:
                raise
            except FileExistsError as exc:
                raise HTTPException(status_code=409, detail=f"{filename} already exists, try again") from exc
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail="Permission denied") from exc
            except OSError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            uploaded.append(build_file_item(config, target).to_dict())
        return {"uploaded": uploaded}

    @app.post("/api/mkdir")
    async def api_mkdir(request: Request) -> dict[str, Any]:
        ensure_write_enabled()
        payload = await read_payload(request)
        directory = safe_resolve(config, str(payload.get("path", "")))
        name = str(payload.get("name", ""))
        item = create_directory(config, directory, name)
        return {"item": item.to_dict()}

    @app.post("/api/rename")
    async def api_rename(request: Request) -> dict[str, Any]:
        ensure_write_enabled()
        payload = await read_payload(request)
        target = safe_resolve(config, str(payload.get("path", "")), follow_final=False)
        name = str(payload.get("new_name", ""))
        old = relative_path(config, target)
        item = rename_path(config, target, name)
        tag_store.move(old, item.relative_path)
        return {"item": with_tags([item])[0].to_dict()}

    @app.post("/api/move")
    async def api_move(request: Request) -> dict[str, Any]:
        ensure_write_enabled()
        payload = await read_payload(request)
        target = safe_resolve(config, str(payload.get("path", "")), follow_final=False)
        destination = safe_resolve(config, str(payload.get("dest", "")))
        old = relative_path(config, target)
        item = move_path(config, target, destination)
        tag_store.move(old, item.relative_path)
        return {"item": with_tags([item])[0].to_dict()}

    @app.post("/api/tags")
    async def api_tags(request: Request) -> dict[str, Any]:
        ensure_write_enabled()
        payload = await read_payload(request)
        target = safe_resolve(config, str(payload.get("path", "")), follow_final=False)
        tags = payload.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise HTTPException(status_code=400, detail="tags must be a list of strings")
        if not os.path.lexists(target):
            raise HTTPException(status_code=404, detail="Item not found")
        rel = relative_path(config, target)
        return {"path": rel, "tags": tag_store.set(rel, tags)}

    @app.post("/api/delete")
    async def api_delete(request: Request) -> dict[str, Any]:
        ensure_write_enabled()
        payload = await read_payload(request)
        path = str(payload.get("path", ""))
        if not delete_is_confirmed(payload.get("confirm")):
            raise HTTPException(status_code=400, detail="Delete confirmation is required")
        target = safe_resolve(config, path, follow_final=False)
        delete_path(config, target)
        tag_store.move(relative_path(config, target), None)
        return {"deleted": path}

    async def run_search(q: str, start: Path) -> tuple[list[FileItem], bool]:
        # The walk is blocking disk IO: run it in a thread so it can't freeze the event loop (and ^C).
        deadline = time.monotonic() + SEARCH_TIME_LIMIT
        cancelled = threading.Event()
        try:
            items = await asyncio.to_thread(
                search_files, config, q, start, lambda: cancelled.is_set() or time.monotonic() > deadline
            )
        finally:
            cancelled.set()  # request cancelled (shutdown): stop the thread instead of letting it run on
        return items, time.monotonic() > deadline

    def with_tags(items: list[FileItem]) -> list[FileItem]:
        for item in items:
            item.tags = tag_store.get(item.relative_path)
        return items

    def tagged_items(tag: str) -> list[FileItem]:
        items = []
        for rel in tag_store.with_tag(tag):
            try:
                path = safe_resolve(config, rel, follow_final=False)
            except HTTPException:
                continue
            if os.path.lexists(path):
                items.append(build_file_item(config, path))
        items.sort(key=lambda item: (item.type != "folder", item.name.casefold()))
        return items

    return app


def template_context(request: Request, **extra: Any) -> dict[str, Any]:
    config: AppConfig = request.app.state.config
    context: dict[str, Any] = {
        "request": request,
        "config": config,
        "root_display": str(config.root),
        "root_name": config.root.name or str(config.root),
        "view_mode": "grid" if request.cookies.get("sb_view") == "grid" else "list",
        "readonly": config.readonly,
        "token_enabled": bool(config.token),
        "current_path": "",
        "tag_colors": TAG_COLORS,
        "mode": "folder",
    }
    context.update(extra)
    return context


def render_template(request: Request, name: str, status_code: int = 200, **extra: Any):
    return templates.TemplateResponse(
        request,
        name,
        template_context(request, **extra),
        status_code=status_code,
    )


def build_breadcrumbs(path: str) -> list[dict[str, str]]:
    crumbs = [{"name": "Root", "path": ""}]
    current: list[str] = []
    parts = [part for part in path.split("/") if part]
    for part in parts:
        current.append(part)
        crumbs.append({"name": part, "path": "/".join(current)})
    return crumbs


def require_file(config: AppConfig, path: str) -> Path:
    target = safe_resolve(config, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")
    return target


def delete_is_confirmed(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes", "on"}
    return False


async def read_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        return payload
    form = await request.form()
    return dict(form)

from __future__ import annotations

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
    auto_rename_target,
    build_file_item,
    child_directories,
    create_directory,
    delete_path,
    guess_mime_type,
    list_directory,
    read_text_preview,
    relative_path,
    rename_path,
)
from .search import search_files
from .security import AUTH_COOKIE_NAME, request_has_valid_token, safe_resolve, validate_upload_filename


PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="ServeBox")
    app.state.config = config
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
        return templates.TemplateResponse(request, "login.html", {"next": next, "error": None})

    @app.post("/login", response_class=HTMLResponse)
    async def login(request: Request, token: str = Form(...), next: str = Form("/")) -> HTMLResponse:
        if not config.token:
            return RedirectResponse("/", status_code=303)
        if request_has_valid_token(request, config) or token == config.token:
            response = RedirectResponse(next or "/", status_code=303)
            response.set_cookie(
                AUTH_COOKIE_NAME,
                config.token,
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 30,
            )
            return response
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": "Invalid token"},
            status_code=401,
        )

    @app.post("/logout")
    async def logout() -> RedirectResponse:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(AUTH_COOKIE_NAME)
        return response

    @app.get("/browse", response_class=HTMLResponse)
    async def browse(request: Request, path: str = "") -> HTMLResponse:
        directory = safe_resolve(config, path)
        if not directory.exists():
            raise HTTPException(status_code=404, detail="Directory not found")
        if not directory.is_dir():
            return RedirectResponse(f"/view?path={urllib.parse.quote(path)}", status_code=303)
        items = list_directory(config, directory)
        current_path = relative_path(config, directory)
        return render_template(
            request,
            "browse.html",
            current_path=current_path,
            items=items,
            breadcrumbs=build_breadcrumbs(current_path),
        )

    @app.get("/view", response_class=HTMLResponse)
    async def view_file(request: Request, path: str) -> HTMLResponse:
        target = safe_resolve(config, path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="File not found")
        if target.is_dir():
            return RedirectResponse(f"/browse?path={urllib.parse.quote(relative_path(config, target))}", status_code=303)
        item = build_file_item(config, target)
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
        return FileResponse(
            target,
            filename=target.name,
            media_type=guess_mime_type(target) or "application/octet-stream",
            content_disposition_type="inline",
        )

    @app.get("/api/list")
    async def api_list(path: str = "") -> dict[str, Any]:
        directory = safe_resolve(config, path)
        items = [item.to_dict() for item in list_directory(config, directory)]
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
        results = [item.to_dict() for item in search_files(config, q, start)]
        return {"query": q, "scope": scope, "results": results, "limit": config.max_search_results}

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
            target = target.resolve(strict=False)
            total = 0
            try:
                async with aiofiles.open(target, "wb") as handle:
                    while chunk := await upload.read(1024 * 1024):
                        total += len(chunk)
                        if total > config.max_upload_bytes:
                            await handle.close()
                            target.unlink(missing_ok=True)
                            raise HTTPException(status_code=413, detail=f"{filename} exceeds upload limit")
                        await handle.write(chunk)
            except HTTPException:
                raise
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
        target = safe_resolve(config, str(payload.get("path", "")))
        name = str(payload.get("new_name", ""))
        item = rename_path(config, target, name)
        return {"item": item.to_dict()}

    @app.post("/api/delete")
    async def api_delete(request: Request) -> dict[str, Any]:
        ensure_write_enabled()
        payload = await read_payload(request)
        path = str(payload.get("path", ""))
        if not delete_is_confirmed(payload.get("confirm")):
            raise HTTPException(status_code=400, detail="Delete confirmation is required")
        target = safe_resolve(config, path)
        delete_path(config, target)
        return {"deleted": path}

    return app


def template_context(request: Request, **extra: Any) -> dict[str, Any]:
    config: AppConfig = request.app.state.config
    context: dict[str, Any] = {
        "request": request,
        "config": config,
        "root_display": str(config.root),
        "readonly": config.readonly,
        "token_enabled": bool(config.token),
        "current_path": "",
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

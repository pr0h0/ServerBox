from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from servebox.app import create_app
from servebox.config import AppConfig


def post_json(app, path: str, payload: dict[str, Any]) -> tuple[int, bytes]:
    async def run_request() -> tuple[int, bytes]:
        body = json.dumps(payload).encode("utf-8")
        messages = [
            {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }
        ]
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": b"",
                "headers": [
                    (b"host", b"testserver"),
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )

        status = next(message["status"] for message in sent if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"") for message in sent if message["type"] == "http.response.body"
        )
        return status, response_body

    return asyncio.run(run_request())


def test_delete_accepts_boolean_confirmation_without_path_retyping(tmp_path: Path) -> None:
    target = tmp_path / "remove-me.txt"
    target.write_text("delete me")
    app = create_app(AppConfig(root=tmp_path))

    status, _body = post_json(app, "/api/delete", {"path": "remove-me.txt", "confirm": True})

    assert status == 200
    assert not target.exists()


def test_delete_rejects_missing_confirmation(tmp_path: Path) -> None:
    target = tmp_path / "keep-me.txt"
    target.write_text("keep me")
    app = create_app(AppConfig(root=tmp_path))

    status, _body = post_json(app, "/api/delete", {"path": "keep-me.txt"})

    assert status == 400
    assert target.exists()

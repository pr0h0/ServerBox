from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .config import DEFAULT_EXCLUDE_DIRS, AppConfig


def parse_exclude(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ServeBox local file browser")
    parser.add_argument("root", type=Path, help="Root directory to expose as /")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host, default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=9999, help="Bind port, default: 9999")
    parser.add_argument("--token", default=None, help="Require this token for browser access")
    parser.add_argument("--readonly", action="store_true", help="Disable upload, mkdir, rename, and delete")
    parser.add_argument("--show-hidden", action="store_true", help="Show dotfiles and dot directories")
    parser.add_argument("--max-upload-mb", type=int, default=512, help="Maximum upload size per file in MB")
    parser.add_argument("--max-preview-mb", type=int, default=5, help="Maximum text preview size in MB")
    parser.add_argument("--max-search-results", type=int, default=500, help="Maximum recursive search results")
    parser.add_argument(
        "--exclude",
        default=",".join(sorted(DEFAULT_EXCLUDE_DIRS)),
        help="Comma-separated directory names excluded from recursive search",
    )
    parser.add_argument(
        "--allow-no-token-on-lan",
        action="store_true",
        help="Allow binding to 0.0.0.0 without token auth",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.host == "0.0.0.0" and not args.token and not args.allow_no_token_on_lan:
        parser.error(
            "Binding to 0.0.0.0 exposes files to your LAN. Use --token or pass --allow-no-token-on-lan."
        )
    if args.host == "0.0.0.0" and not args.token:
        print(
            "WARNING: ServeBox is bound to 0.0.0.0 without token auth; files may be visible on your LAN.",
            file=sys.stderr,
        )

    try:
        config = AppConfig(
            root=args.root,
            host=args.host,
            port=args.port,
            token=args.token,
            readonly=args.readonly,
            show_hidden=args.show_hidden,
            max_upload_mb=args.max_upload_mb,
            max_preview_mb=args.max_preview_mb,
            max_search_results=args.max_search_results,
            exclude_dirs=parse_exclude(args.exclude),
            allow_no_token_on_lan=args.allow_no_token_on_lan,
        )
    except ValueError as exc:
        parser.error(str(exc))

    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)

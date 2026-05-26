# ServeBox Usage Guide

This guide covers installing ServeBox, running it safely, all supported CLI flags, and common examples.

## Install

ServeBox requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On systems where Python is exposed as `python3`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Basic Run

Serve a directory with:

```bash
python -m servebox <root-directory> --port 9999
```

The root directory becomes `/` in the browser. For example:

```bash
python -m servebox ~/Downloads --port 9999
```

Then open:

```txt
http://127.0.0.1:9999
```

## All CLI Flags

```txt
root                         Required. Directory exposed as / in the web UI.
--host HOST                  Bind host. Default: 127.0.0.1.
--port PORT                  Bind port. Default: 9999.
--token TOKEN                Require token auth for UI, file, and API routes.
--readonly                   Disable upload, mkdir, rename, and delete.
--show-hidden                Show dotfiles and dot directories.
--max-upload-mb MB           Maximum upload size per file. Default: 512.
--max-preview-mb MB          Maximum text preview size. Default: 5.
--max-search-results COUNT   Maximum recursive search results. Default: 500.
--exclude NAMES              Comma-separated directory names skipped by search.
--allow-no-token-on-lan      Allow --host 0.0.0.0 without --token.
```

Default excluded search directories:

```txt
.git,node_modules,__pycache__,venv,.venv,dist,build,target,.idea,.vscode
```

## Run Examples

Serve your home directory on localhost:

```bash
python -m servebox ~/ --host 127.0.0.1 --port 9999
```

Serve the current directory:

```bash
python -m servebox . --port 9999
```

Serve Downloads in readonly mode:

```bash
python -m servebox ~/Downloads --readonly
```

Serve Downloads and show hidden files:

```bash
python -m servebox ~/Downloads --show-hidden
```

Serve to your LAN with token auth:

```bash
python -m servebox ~/Downloads --host 0.0.0.0 --port 9999 --token mysecret
```

Open with the token in the URL:

```txt
http://<machine-ip>:9999/browse?token=mysecret
```

Serve to LAN without token auth, only if you accept the risk:

```bash
python -m servebox ~/Downloads --host 0.0.0.0 --port 9999 --allow-no-token-on-lan
```

Limit upload size to 100 MB per file:

```bash
python -m servebox ~/Downloads --max-upload-mb 100
```

Limit text previews to the first 2 MB:

```bash
python -m servebox ~/Downloads --max-preview-mb 2
```

Limit search results:

```bash
python -m servebox ~/Downloads --max-search-results 100
```

Customize excluded search directories:

```bash
python -m servebox ~/Projects --exclude .git,node_modules,.cache,tmp
```

## Web UI

The top bar shows the app name, selected root path, write mode, search, and logout when token auth is enabled.

The sidebar lazily loads child folders. It does not recursively load the full directory tree on page load.

The main browser includes:

- Breadcrumb navigation.
- Current directory filter.
- Upload button and drag/drop zone when not readonly.
- File table with name, type, size, modified time, and actions.
- View, download, copy path, rename, and delete actions.

Delete uses a confirm modal. It does not require typing the full path.

## Search

The search box in the top bar performs case-insensitive recursive filename search. It behaves like:

```bash
find . -iname "*query*"
```

Search can run from the root or the current directory, depending on the scope selector. It skips excluded directory names and stops at `--max-search-results`.

## Uploads

Uploads are allowed unless `--readonly` is set.

ServeBox supports:

- Multiple file selection.
- Drag and drop.
- Per-file upload limit through `--max-upload-mb`.
- Safe filename validation.
- Auto-renaming instead of overwriting.

If `file.txt` already exists, uploads become:

```txt
file (1).txt
file (2).txt
```

## Previews

ServeBox previews common file types:

- Text and code files in a monospace viewer.
- Images inline.
- PDFs in an embedded viewer.
- Audio through an HTML5 audio player.
- Video through an HTML5 video player.

Unknown or binary files show metadata and a download action.

Text previews are limited by `--max-preview-mb`.

## Token Auth

When `--token` is set, ServeBox requires authentication.

You can log in through:

```txt
http://127.0.0.1:9999/login
```

Or include the token in a direct URL:

```txt
http://127.0.0.1:9999/browse?token=mysecret
```

The login stores the token in an HTTP-only cookie.

## Readonly Mode

Readonly mode disables write operations:

```bash
python -m servebox ~/Downloads --readonly
```

Disabled operations:

- Upload.
- Create folder.
- Rename.
- Delete.

Browsing, previewing, downloading, and searching still work.

## Security Model

ServeBox confines every request to the configured root directory.

The safe resolver:

- Treats browser paths as relative paths under the root.
- Rejects absolute paths.
- Rejects null bytes and malformed paths.
- Resolves `..` traversal.
- Resolves symlinks.
- Allows access only when the resolved target is the root or inside it.

Symlinks that point outside the root are blocked.

## Troubleshooting

If `python` is not found, use `python3`.

If `pytest` or FastAPI imports fail, install dependencies:

```bash
pip install -r requirements.txt
```

If port `9999` is already in use, choose another port:

```bash
python -m servebox ~/Downloads --port 10000
```

If another device cannot connect, check:

- ServeBox is running with `--host 0.0.0.0`.
- The URL uses the machine IP, not `127.0.0.1`.
- A firewall is not blocking the port.
- Token auth is included or you are logged in.

## Development

Run tests:

```bash
pytest
```

Run with dependencies through `uv` if your system Python has no venv or pip:

```bash
uv run --with fastapi --with uvicorn --with jinja2 --with python-multipart --with aiofiles --with pytest python -m pytest -q
```

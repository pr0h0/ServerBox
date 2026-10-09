# ServeBox

ServeBox is a local/private file browser and file server for a selected root directory. It behaves like `python -m http.server 9999` with a web UI for safe browsing, previews, downloads, uploads, folder creation, rename, delete, lazy directory trees, and recursive search.

ServeBox treats the directory you choose at startup as `/` in the browser. It uses one central safe path resolver for UI routes, file routes, and API routes so requests cannot escape that root through absolute paths, `..` traversal, or symlinks that point outside the root.

## Quick Start

Use Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m servebox ~/ --port 9999
```

If your system command is `python3`, use:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m servebox ~/ --port 9999
```

Open the printed URL in your browser.

## Common Examples

Serve your home directory locally:

```bash
python -m servebox ~/ --port 9999
```

Serve Downloads on localhost:

```bash
python -m servebox ~/Downloads --host 127.0.0.1 --port 9999
```

Serve Downloads to your LAN with token auth:

```bash
python -m servebox ~/Downloads --host 0.0.0.0 --port 9999 --token mysecret
```

Run in readonly mode:

```bash
python -m servebox ~/Downloads --readonly
```

Show hidden files:

```bash
python -m servebox ~/Downloads --show-hidden
```

## Documentation

- [Usage Guide](docs/usage.md): install, run commands, all flags, UI behavior, examples, and troubleshooting.

## Features

- Finder-style UI: icon and list views, sortable columns, sidebar, path bar, dark mode, and a phone-friendly layout.
- Right-click context menus, multi-select, keyboard shortcuts, and Quick Look (Space).
- Finder color tags, with a sidebar view per tag.
- Drag items onto folders to move them; drag files in from your desktop to upload with progress.
- Lazy-loaded sidebar directory tree.
- Recursive case-insensitive search with result limits, shown in the main view.
- Hidden file filtering unless `--show-hidden` is used.
- Upload by file picker or drag and drop.
- Upload auto-rename with `file (1).txt` style names.
- Text, image, PDF, audio, and video previews.
- Download and raw inline file serving.
- Folder creation, rename, move, and confirm-modal delete when not readonly.
- Token login and `?token=...` access for shared links.
- JSON APIs for list, tree, search, upload, mkdir, rename, move, tags, and delete.
- Hardened defaults: sandboxed raw files, strict CSP, CSRF origin checks, hashed session cookie.

## CLI Options

```txt
root                         Directory exposed as /
--host                       Bind host, default 127.0.0.1
--port                       Bind port, default 9999
--token                      Require token login and token query access
--readonly                   Disable upload, mkdir, rename, and delete
--show-hidden                Show dotfiles and dot directories
--max-upload-mb              Max upload size per file, default 512
--max-preview-mb             Max text preview size, default 5
--max-search-results         Max recursive search results, default 500
--exclude                    Comma-separated directory names skipped by search
--allow-no-token-on-lan      Permit 0.0.0.0 without a token
```

The default search excludes:

```txt
.git,node_modules,__pycache__,venv,.venv,dist,build,target,.idea,.vscode
```

## Security Notes

ServeBox is designed for local/private use. It is not a public internet file manager.

Binding to `0.0.0.0` exposes ServeBox to your LAN. ServeBox refuses to bind to `0.0.0.0` without `--token` unless you explicitly pass `--allow-no-token-on-lan`.

When `--token` is set, ServeBox accepts either a login through `/login` or a `?token=...` query parameter. The login stores the token in an HTTP-only cookie.

## License

ServeBox is licensed under the [MIT License](LICENSE).

## Development

Run tests:

```bash
pytest
```

If dependencies are not installed:

```bash
pip install -r requirements.txt
pytest
```

Run a local development instance:

```bash
python -m servebox . --port 9999 --show-hidden
```

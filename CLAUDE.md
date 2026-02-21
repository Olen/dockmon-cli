# dockmon-cli

CLI tool for monitoring Docker containers via a remote dockmon API server.

## Project structure

- `dockmon_cli.py` — single-file CLI tool, installed as `dockmon-cli` console script
- `pyproject.toml` — package metadata, dependency: `requests`

## API

- Connects to a [dockmon](https://github.com/darthnorse/dockmon) FastAPI server
- All endpoints under `/api/` prefix (e.g. `/api/hosts`, `/api/containers`)
- Auth: Bearer token (`dockmon_<base64url>` format)
- `DOCKMON_API_URL` should end with `/api`

## Credentials

Resolved in order: env vars > `~/.config/dockmon/config.ini` > Docker secrets.
No private dependencies — 1Password integration is handled by a local wrapper script outside this repo.

## Origin

- GitHub: github.com/Olen/dockmon-cli (public)

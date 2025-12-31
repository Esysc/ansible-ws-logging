# Real-Time Ansible Logs Viewer 🔍

<img width="1303" height="777" alt="image" src="https://github.com/user-attachments/assets/21730993-d0a2-4a52-910e-431b94f5c969" />

A small Flask + Flask-SocketIO app that streams Ansible logs in
real time to connected web clients.

## Features

- **Real-Time Log Streaming**: View logs as they are generated
  during Ansible playbook execution.
- **Live File Monitoring**: Uses `watchdog` to detect new/modified
  log files.
- **Auto Port Fallback**: If the initial port is occupied, the server
  checks the next ports until it finds a free one (configurable).

## Prerequisites

- **Python 3.10+ recommended** — Python 3.14 has been
  tested and is supported in this project.
- pip, virtualenv / venv
- On macOS, ensure build tools are available for C extensions: `xcode-select --install`

## Install (local dev)

```bash
git clone https://github.com/Esysc/ansible-ws-logging
cd ansible-ws-logging
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

(If you see build errors for native extensions, ensure Xcode command
line tools are installed on macOS.)
```

## Configuration (environment variables)

- `ANSIBLE_LOGS_DIR` — root logs directory (default: `/var/log/ansible`)
- `SECRET_KEY` — Flask secret (default: `secret!`; **set in production**)
- `INITIAL_PORT` — initial port to try (default: `5000`)
- `MAX_PORT_TRIES` — how many consecutive ports to try (default: `20`)

Example:

```bash
export ANSIBLE_LOGS_DIR="/path/to/your/logs"
export SECRET_KEY="replace-with-secure-value"
export INITIAL_PORT=5000
export MAX_PORT_TRIES=50
# Run with environment variables
python app.py

# Or override using command-line options (CLI overrides env vars)
python app.py \
  --initial-port 6000 --max-port-tries 10 --host 127.0.0.1 --no-debug
```

## Usage

1. Start the app (env vars):

```bash
python app.py
```

1. Or start with CLI options (overrides env vars):

```bash
python app.py \
  --initial-port 6000 \
  --max-port-tries 10 \
  --host 127.0.0.1
```

1. Open the URL printed by the server (e.g.,
   `http://localhost:5000`) or the fallback port it reports.

> The server performs a short bind check before starting and will
  print which port it uses if the initial port was occupied.

## Troubleshooting

- If you see "Address already in use", the app will try the next
  port automatically — check the server output for the final port.
- On macOS with very new Python versions, C extension builds (e.g.,
  `greenlet`) can fail. If you hit build issues, try using a supported
  Python version (3.11/3.12/3.14) or upgrade `greenlet`.
- If the web UI doesn't show logs, verify `ANSIBLE_LOGS_DIR` is set
  correctly and the app can read the files.

## Testing ✅

We provide an Ansible playbook that runs static checks and unit tests locally.
It uses a local `venv` by default.

```bash
# Run the test playbook (runs: mypy, flake8, pytest)
ansible-playbook tests/playbook.yml
```

The playbook will create a virtualenv at `tests/.venv`, install the
project requirements and test tools (`pytest`, `mypy`, `flake8`), and
then run them. You can also run the checks manually:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt pytest mypy flake8
python -m mypy app.py
flake8 .
pytest -q
```

If you want CI integration, add a workflow that runs the same commands.

## Production

- Use a production-ready WSGI server or container (e.g.,
  `gunicorn` with `eventlet` workers) for deployment.
- Ensure `SECRET_KEY` is set and logs directory permissions are correct.

## Contributing

Contributions welcome: open issues or PRs; include tests where applicable.

### Pre-commit hooks

This repository uses `pre-commit` to run linters and formatting on
changed files. We added a Markdown linter that can automatically fix
issues and **ruff** to auto-format and lint Python code on commit.

Install and enable hooks:

```bash
python -m pip install --upgrade pre-commit
pre-commit install
```

Run all hooks locally (including auto-fixes from ruff):

```bash
# Runs all configured hooks across the repo
pre-commit run --all-files
# Or run ruff alone (ruff will auto-fix when configured with --fix)
pre-commit run ruff --all-files
```

If you prefer to use the markdown linter directly, you can also
install `markdownlint-cli` (node) or use the Docker image.

---

If you'd like, I can also add a short note to the top of the app
or a `--help` printout that reports the selected port on startup.

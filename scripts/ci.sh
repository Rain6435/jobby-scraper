#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Resolve python interpreter
if [ -f "$REPO_ROOT/../venv/bin/python3" ]; then
    PYTHON="$REPO_ROOT/../venv/bin/python3"
elif [ -f "$REPO_ROOT/../venv/bin/python" ]; then
    PYTHON="$REPO_ROOT/../venv/bin/python"
elif [ -f "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "No python interpreter found" >&2
    exit 1
fi

export PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}"

echo "=== 1. Running Tests (pytest) ==="
if "$PYTHON" -m pytest -n auto --help &>/dev/null; then
    "$PYTHON" -m pytest -n auto -q
else
    "$PYTHON" -m pytest -q
fi

echo "=== 2. Type Checking (pyright --strict) ==="
if [ -f "$REPO_ROOT/.venv/bin/pyright" ]; then
    "$REPO_ROOT/.venv/bin/pyright"
elif command -v pyright &>/dev/null; then
    pyright
elif [ -f "$HOME/.local/bin/pyright" ]; then
    "$HOME/.local/bin/pyright"
else
    "$PYTHON" -m pyright
fi

echo "=== 3. Strict Type Audit (No Any, no suppression comments) ==="
if grep -rn '\bAny\b' scraper tests; then
  echo "Found 'Any' — this repo is strict-typed with zero Any allowed" >&2
  exit 1
fi
if grep -rn 'type: ignore\|pyright: ignore' scraper tests; then
  echo "Found a type-check suppression comment — fix the real type instead" >&2
  exit 1
fi

echo "=== 4. Code Formatting (ruff format --check) ==="
if [ -f "$REPO_ROOT/.venv/bin/ruff" ]; then
    RUFF="$REPO_ROOT/.venv/bin/ruff"
elif command -v ruff &>/dev/null; then
    RUFF="ruff"
elif [ -f "$HOME/.local/bin/ruff" ]; then
    RUFF="$HOME/.local/bin/ruff"
else
    RUFF="$PYTHON -m ruff"
fi
$RUFF format --check .

echo "=== 5. Linting (ruff check) ==="
$RUFF check .

echo " All CI checks passed successfully!"

"""API keys from the environment or the project .env file. A key value is never printed, logged or put in an
error message (PLAN 5.4).

The .env file holds one NAME=value line per key:
    ANTHROPIC_API_KEY=...
    OPENROUTER_API_KEY=...
    HF_TOKEN=...
"""
from __future__ import annotations

import os
from pathlib import Path

from pipeline import config

ENV_FILE = config.ROOT / ".env"
KEY_NAMES = {"anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY", "hf": "HF_TOKEN"}


class MissingKey(RuntimeError):
    pass


def load_env(path=None) -> list[str]:
    """Read NAME=value lines into the environment without replacing a value already set. Blank lines, comments
    and an 'export ' prefix are allowed, and matching quotes around a value are removed. Returns the names read,
    never the values."""
    path = Path(path or ENV_FILE)
    if not path.exists():
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        name, eq, value = line.partition("=")
        name = name.strip()
        if not eq or not name.isidentifier():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if not os.environ.get(name):
            os.environ[name] = value
        names.append(name)
    return names


def key(api: str) -> str:
    name = KEY_NAMES[api]
    if not os.environ.get(name):
        load_env()
    value = os.environ.get(name)
    if not value:
        raise MissingKey(f"{name} is not set; add it to {ENV_FILE} or export it in the shell")
    return value

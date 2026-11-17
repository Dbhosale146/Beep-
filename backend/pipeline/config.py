"""Loads YAML config. One place, so paths are never hardcoded in modules."""

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def load_env(path: str = ".env") -> None:
    """Read KEY=VALUE lines from .env into os.environ, without overwriting.

    Ten lines instead of a python-dotenv dependency. In GitHub Actions there is
    no .env at all; the secrets are already real env vars and this is a no-op.
    """
    f = ROOT / path
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def require_env(name: str) -> str:
    """Fetch a secret or fail with a message that says what to do."""
    load_env()
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Add it to .env (see .env.example) "
            f"or set it as a GitHub Actions secret."
        )
    return value


def load_yaml(filename: str) -> dict:
    with open(CONFIG_DIR / filename, encoding="utf-8") as f:
        return yaml.safe_load(f)


def settings() -> dict:
    return load_yaml("settings.yaml")


def companies() -> dict:
    return load_yaml("companies.yaml")


def taxonomy() -> dict:
    return load_yaml("taxonomy.yaml")


def data_path(key: str) -> Path:
    """Turn a settings.paths key into an absolute path, making the dir."""
    p = ROOT / settings()["paths"][key]
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

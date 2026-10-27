"""Configuration from the environment, validated once at startup (twelve-factor). Secrets only from here."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class ConfigurationError(ValueError):
    """An environment variable is missing or has an unusable value."""


def _text(environ: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = environ.get(name, default if default is not None else "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set and not empty")
    return value


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name, str(default)).strip()
    if not raw.isdigit() or int(raw) < 1:
        raise ConfigurationError(f"{name} must be a positive integer, got {raw!r}")
    return int(raw)


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    """The PostgreSQL part of the configuration; the password is never printed."""

    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)  # never printed or logged
    schema: str
    connect_timeout_seconds: int
    statement_timeout_ms: int


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the programs read from the environment. See .env.example for each variable."""

    postgres: PostgresSettings
    log_level: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        level = _text(env, "LOG_LEVEL", "INFO").upper()
        if level not in _LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(_LEVELS)}, got {level!r}")
        schema = _text(env, "POSTGRES_SCHEMA", "public")
        if not _IDENTIFIER.match(schema):
            raise ConfigurationError(f"POSTGRES_SCHEMA must be a lower-case identifier, got {schema!r}")
        return cls(
            postgres=PostgresSettings(
                host=_text(env, "POSTGRES_HOST", "localhost"),
                port=_positive_int(env, "POSTGRES_PORT", 5441),
                database=_text(env, "POSTGRES_DB", "rentals"),
                user=_text(env, "POSTGRES_USER", "shop"),
                password=_text(env, "POSTGRES_PASSWORD"),
                schema=schema,
                connect_timeout_seconds=_positive_int(env, "POSTGRES_CONNECT_TIMEOUT_SECONDS", 5),
                statement_timeout_ms=_positive_int(env, "POSTGRES_STATEMENT_TIMEOUT_MS", 30_000),
            ),
            log_level=level,
        )

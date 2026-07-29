"""Application configuration, loaded from environment variables.

Configuration is read once at startup and passed explicitly to whatever needs it.
Nothing else in the package reads os.environ - that keeps every other module
testable without monkeypatching the environment, and makes the full set of
tunable values visible in one place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_SOURCE_ORDER = ("google_patents",)
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_OUTPUT_DIR = Path("output")


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime settings for the application."""

    source_order: tuple[str, ...] = DEFAULT_SOURCE_ORDER
    http_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    output_dir: Path = DEFAULT_OUTPUT_DIR
    epo_ops_key: str | None = None
    epo_ops_secret: str | None = None

    @property
    def has_epo_credentials(self) -> bool:
        return bool(self.epo_ops_key and self.epo_ops_secret)


def _env_float(name: str, default: float) -> float:
    """Read a float, falling back to the default rather than crashing on garbage.

    A malformed timeout should not prevent the application from starting.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_config(env_file: Path | None = None) -> Config:
    """Build a Config from the environment, loading a .env file if present.

    Real environment variables win over .env values, which is what you want in
    production where secrets come from the deployment environment.
    """
    load_dotenv(dotenv_path=env_file, override=False)

    raw_order = os.getenv("PATENT_SOURCE_ORDER", "")
    order = tuple(name.strip() for name in raw_order.split(",") if name.strip())

    return Config(
        source_order=order or DEFAULT_SOURCE_ORDER,
        http_timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        output_dir=Path(os.getenv("OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))),
        epo_ops_key=os.getenv("EPO_OPS_KEY") or None,
        epo_ops_secret=os.getenv("EPO_OPS_SECRET") or None,
    )

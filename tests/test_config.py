"""Tests for configuration loading and the source registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from patent_retriever.config import DEFAULT_SOURCE_ORDER, Config, load_config
from patent_retriever.sources.registry import available_source_names, build_sources


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PATENT_SOURCE_ORDER",
        "HTTP_TIMEOUT_SECONDS",
        "OUTPUT_DIR",
        "EPO_OPS_KEY",
        "EPO_OPS_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_apply_when_environment_is_empty() -> None:
    config = load_config(env_file=Path("/nonexistent"))
    assert config.source_order == DEFAULT_SOURCE_ORDER
    assert config.http_timeout_seconds == 20.0
    assert not config.has_epo_credentials


def test_source_order_is_parsed_and_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATENT_SOURCE_ORDER", " google_patents , epo_ops ")
    config = load_config(env_file=Path("/nonexistent"))
    assert config.source_order == ("google_patents", "epo_ops")


def test_blank_source_order_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATENT_SOURCE_ORDER", " , , ")
    assert load_config(env_file=Path("/nonexistent")).source_order == DEFAULT_SOURCE_ORDER


def test_malformed_timeout_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "not-a-number")
    assert load_config(env_file=Path("/nonexistent")).http_timeout_seconds == 20.0


def test_epo_credentials_require_both_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPO_OPS_KEY", "key")
    assert not load_config(env_file=Path("/nonexistent")).has_epo_credentials
    monkeypatch.setenv("EPO_OPS_SECRET", "secret")
    assert load_config(env_file=Path("/nonexistent")).has_epo_credentials


def test_registry_builds_configured_sources() -> None:
    sources = build_sources(Config(source_order=("google_patents",)))
    assert len(sources) == 1
    assert sources[0].name == "google_patents"


def test_registry_rejects_unknown_source_names() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        build_sources(Config(source_order=("does_not_exist",)))


def test_registry_builds_epo_ops_when_credentials_are_present() -> None:
    config = Config(source_order=("epo_ops",), epo_ops_key="key", epo_ops_secret="secret")
    assert build_sources(config)[0].name == "epo_ops"


@pytest.mark.parametrize(
    ("key", "secret", "expected"),
    [
        (None, None, "EPO_OPS_KEY and EPO_OPS_SECRET are not set"),
        ("key", None, "EPO_OPS_SECRET is not set"),
        (None, "secret", "EPO_OPS_KEY is not set"),
    ],
)
def test_registry_names_the_missing_epo_variables(
    key: str | None, secret: str | None, expected: str
) -> None:
    config = Config(source_order=("epo_ops",), epo_ops_key=key, epo_ops_secret=secret)
    with pytest.raises(ValueError, match=expected):
        build_sources(config)


def test_available_source_names_is_not_empty() -> None:
    assert "google_patents" in available_source_names()
    assert "epo_ops" in available_source_names()

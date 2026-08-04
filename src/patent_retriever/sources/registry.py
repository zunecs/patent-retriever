"""Builds source instances from their configured names.

The retrieval service takes source objects, but configuration supplies strings.
This module is the single place that translates between the two - which is what
keeps the service unaware of which sources exist.

Adding a source means adding one entry to _BUILDERS. Nothing else changes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from patent_retriever.config import Config
from patent_retriever.sources.base import PatentSource
from patent_retriever.sources.epo_ops import EpoOpsSource
from patent_retriever.sources.google_patents import GooglePatentsSource

SourceBuilder = Callable[[Config], PatentSource]


def _build_epo_ops(config: Config) -> PatentSource:
    """EPO OPS needs credentials, so its failure mode is a clear configuration error.

    The message names the variables that are actually missing rather than both,
    because "set EPO_OPS_KEY and EPO_OPS_SECRET" is unhelpful when one of them
    already is set and the other was mistyped.
    """
    missing = [
        name
        for name, value in (
            ("EPO_OPS_KEY", config.epo_ops_key),
            ("EPO_OPS_SECRET", config.epo_ops_secret),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            f"epo_ops is configured but {' and '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} not set. "
            "Register at https://developers.epo.org/ and put the credentials in .env"
        )
    return EpoOpsSource(
        key=config.epo_ops_key or "",
        secret=config.epo_ops_secret or "",
        timeout=config.http_timeout_seconds,
    )


_BUILDERS: dict[str, SourceBuilder] = {
    "google_patents": lambda config: GooglePatentsSource(timeout=config.http_timeout_seconds),
    "epo_ops": _build_epo_ops,
}


def available_source_names() -> tuple[str, ...]:
    return tuple(_BUILDERS)


def build_sources(config: Config) -> tuple[PatentSource, ...]:
    """Instantiate the sources named in the configuration, in order.

    Raises:
        ValueError: a configured name has no builder, or none could be built.
    """
    unknown = [name for name in config.source_order if name not in _BUILDERS]
    if unknown:
        raise ValueError(
            f"Unknown source(s): {', '.join(unknown)}. "
            f"Available: {', '.join(available_source_names())}."
        )

    sources: Sequence[PatentSource] = [_BUILDERS[name](config) for name in config.source_order]
    if not sources:
        raise ValueError("No sources configured.")
    return tuple(sources)

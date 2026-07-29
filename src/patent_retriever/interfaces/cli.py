"""Command-line interface.

This layer is deliberately thin: parse arguments, call the service, write files,
report. It contains no retrieval or formatting logic, which is what allows the
Flask interface to reuse everything below it without duplication.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

from patent_retriever.config import load_config
from patent_retriever.domain.exceptions import (
    InvalidPatentNumberError,
    PatentNotFoundError,
)
from patent_retriever.domain.models import RenderOptions
from patent_retriever.renderers.docx_renderer import write_docx
from patent_retriever.renderers.json_renderer import write_json
from patent_retriever.services.retrieval import PatentRetrievalService
from patent_retriever.sources.registry import build_sources

app = typer.Typer(
    help="Retrieve patent documents and render them for the Patent Translation tool.",
    add_completion=False,
)

EXIT_INVALID_INPUT = 2
EXIT_NOT_FOUND = 3
EXIT_CONFIG_ERROR = 4


def _configure_logging(verbose: bool) -> None:
    """Send logs to stderr so stdout stays clean for piping."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


@app.command()
def fetch(
    number: Annotated[str, typer.Argument(help="Patent number, e.g. US20250097171A1")],
    docket: Annotated[str, typer.Option(help="Attorney docket number.")] = "",
    client_ref: Annotated[str, typer.Option(help="Client reference number.")] = "",
    output_dir: Annotated[
        Path | None, typer.Option(help="Where to write output. Defaults to config.")
    ] = None,
    json_only: Annotated[bool, typer.Option(help="Write JSON only, no .docx.")] = False,
    docx_only: Annotated[bool, typer.Option(help="Write .docx only, no JSON.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show progress.")] = False,
) -> None:
    """Retrieve a patent and write the .docx and JSON outputs."""
    _configure_logging(verbose)
    config = load_config()

    try:
        sources = build_sources(config)
    except ValueError as error:
        typer.secho(f"Configuration error: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR) from error

    service = PatentRetrievalService(sources)

    try:
        result = service.retrieve(number)
    except InvalidPatentNumberError as error:
        typer.secho(str(error), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_INVALID_INPUT) from error
    except PatentNotFoundError as error:
        typer.secho(str(error), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_NOT_FOUND) from error

    document = result.document
    options = RenderOptions(attorney_docket_number=docket, client_reference=client_ref)
    target_dir = output_dir or config.output_dir
    stem = document.publication_number

    typer.secho(f"Retrieved {stem} from {result.source_name}", fg=typer.colors.GREEN)
    if not result.is_complete:
        typer.secho(
            f"Warning: missing {', '.join(result.missing_fields)}",
            fg=typer.colors.YELLOW,
            err=True,
        )

    if not json_only:
        path = write_docx(document, target_dir / f"{stem}.docx", options)
        typer.echo(f"  {path}")
    if not docx_only:
        path = write_json(document, target_dir / f"{stem}.json", options, result.source_name)
        typer.echo(f"  {path}")


@app.command()
def sources() -> None:
    """List the configured and available sources."""
    from patent_retriever.sources.registry import available_source_names

    config = load_config()
    typer.echo(f"Configured order: {', '.join(config.source_order)}")
    typer.echo(f"Available:        {', '.join(available_source_names())}")


if __name__ == "__main__":
    app()

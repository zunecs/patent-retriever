"""Flask web interface.

Like the CLI, this layer is thin: parse the form, call the service, render the
result. All retrieval and formatting logic lives below it and is shared with the
CLI - neither interface reimplements anything.

Retrieved documents are cached in process memory so that previewing a patent and
then downloading it does not scrape the source twice. This is adequate for a
single-process internal tool; a multi-worker deployment would need a shared cache
such as Redis, and that is the only change required.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from io import BytesIO

from flask import Flask, Response, abort, render_template, request, send_file

from patent_retriever.config import Config, load_config
from patent_retriever.domain.exceptions import (
    InvalidPatentNumberError,
    PatentNotFoundError,
)
from patent_retriever.domain.models import RenderOptions
from patent_retriever.renderers.docx_renderer import render_docx, render_lines
from patent_retriever.renderers.json_renderer import render_json
from patent_retriever.services.retrieval import PatentRetrievalService, RetrievalResult
from patent_retriever.sources.registry import build_sources

logger = logging.getLogger(__name__)

CACHE_MAX_ENTRIES = 32

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ResultCache:
    """A bounded least-recently-used cache of retrieval results."""

    def __init__(self, max_entries: int = CACHE_MAX_ENTRIES) -> None:
        self._entries: OrderedDict[str, tuple[RetrievalResult, RenderOptions]] = OrderedDict()
        self._max_entries = max_entries

    def put(self, key: str, result: RetrievalResult, options: RenderOptions) -> None:
        self._entries[key] = (result, options)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def get(self, key: str) -> tuple[RetrievalResult, RenderOptions] | None:
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
        return entry


def create_app(config: Config | None = None) -> Flask:
    """Build the Flask application.

    An application factory rather than a module-level `app` object: it lets tests
    construct an isolated instance with injected configuration, and avoids doing
    work at import time.
    """
    app = Flask(__name__)
    app.config["PATENT_CONFIG"] = config or load_config()
    cache = ResultCache()

    def service() -> PatentRetrievalService:
        return PatentRetrievalService(build_sources(app.config["PATENT_CONFIG"]))

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.post("/retrieve")
    def retrieve() -> tuple[str, int] | str:
        number = (request.form.get("number") or "").strip()
        options = RenderOptions(
            attorney_docket_number=(request.form.get("docket") or "").strip(),
            client_reference=(request.form.get("client_ref") or "").strip(),
        )

        if not number:
            return render_template("index.html", error="Enter a patent number."), 400

        try:
            result = service().retrieve(number)
        except InvalidPatentNumberError as error:
            return render_template("index.html", error=str(error), number=number), 400
        except PatentNotFoundError as error:
            return render_template("index.html", error=str(error), number=number), 404

        key = result.document.publication_number
        cache.put(key, result, options)

        return render_template(
            "result.html",
            result=result,
            lines=render_lines(result.document, options),
        )

    def _cached(number: str) -> tuple[RetrievalResult, RenderOptions]:
        entry = cache.get(number)
        if entry is None:
            abort(404, description="Not retrieved yet, or the result has expired.")
        return entry

    @app.get("/download/<number>.docx")
    def download_docx(number: str) -> Response:
        result, options = _cached(number)
        return send_file(
            BytesIO(render_docx(result.document, options)),
            mimetype=DOCX_MIME,
            as_attachment=True,
            download_name=f"{number}.docx",
        )

    @app.get("/download/<number>.json")
    def download_json(number: str) -> Response:
        result, options = _cached(number)
        payload = render_json(result.document, options, result.source_name)
        return send_file(
            BytesIO(payload.encode("utf-8")),
            mimetype="application/json",
            as_attachment=True,
            download_name=f"{number}.json",
        )

    return app


if __name__ == "__main__":
    create_app().run(debug=True)

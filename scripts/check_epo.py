"""Capture EPO OPS fixtures and print their structure.

Run against live OPS with credentials in .env. Everything it writes under
tests/fixtures/ is what the test suite replays, so re-run this - never hand-edit
a fixture - when OPS changes shape.

Every reference below is deliberate. EP3000001 is an ordinary modern EP document
with German, French, and English full text, in that order. EP0000001 is a 1978
document whose English claims OPS serves as a corrupt OCR dump, and whose biblio
returns two publications for one reference. US2025097171 has working biblio but
refuses full text, which is what makes US patents fall through to the next source.
"""

import base64
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(".env")

auth = base64.b64encode(
    f"{os.getenv('EPO_OPS_KEY')}:{os.getenv('EPO_OPS_SECRET')}".encode()
).decode()

token = httpx.post(
    "https://ops.epo.org/3.2/auth/accesstoken",
    headers={
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    },
    data={"grant_type": "client_credentials"},
    timeout=30,
).json()["access_token"]

HEADERS = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
ROOT = "https://ops.epo.org/3.2/rest-services/published-data/publication"
REFERENCES = ("EP3000001", "EP0000001", "US2025097171")

FIXTURES = Path("tests/fixtures")
FIXTURES.mkdir(parents=True, exist_ok=True)


def outline(node: object, depth: int = 0, limit: int = 6) -> None:
    pad = "  " * depth
    if depth > limit:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            leaf = not isinstance(value, dict | list)
            preview = f" = {str(value)[:70]!r}" if leaf else ""
            print(f"{pad}{key}{preview}")
            if not leaf:
                outline(value, depth + 1, limit)
    elif isinstance(node, list):
        print(f"{pad}[list of {len(node)}]")
        if node:
            outline(node[0], depth + 1, limit)


for reference in REFERENCES:
    for service in ("biblio", "claims", "description"):
        response = httpx.get(f"{ROOT}/epodoc/{reference}/{service}", headers=HEADERS, timeout=90)
        header = f"{reference} {service}: {response.status_code}, {len(response.text)} bytes"
        print(f"\n{'=' * 70}\n{header}\n{'=' * 70}")

        if response.status_code != 200:
            # OPS answers faults in XML whatever the Accept header asks for.
            path = FIXTURES / f"epo_{reference}_{service}_fault.xml"
            path.write_text(response.text)
            print(f"saved -> {path}\n{response.text[:300]}")
            continue

        data = response.json()
        path = FIXTURES / f"epo_{reference}_{service}.json"
        path.write_text(json.dumps(data, indent=2))
        print(f"saved -> {path}\n")
        outline(data)

"""Print the structural landmarks of a saved Google Patents page."""

import sys
from pathlib import Path

from bs4 import BeautifulSoup

path = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/US20250097171A1.html")
soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")

print("=== META TAGS ===")
for meta in soup.find_all("meta"):
    name = meta.get("name") or meta.get("property") or ""
    if any(k in name.lower() for k in ("title", "inventor", "patent", "abstract", "date")):
        print(f"{name} = {str(meta.get('content'))[:90]}")

print("\n=== ABSTRACT ===")
for selector in ("abstract", "div.abstract", "section[itemprop=abstract]"):
    found = soup.select(selector)
    print(f"{selector!r}: {len(found)} match(es)")
    if found:
        print("   ", found[0].get_text(" ", strip=True)[:150])

print("\n=== DESCRIPTION ===")
for selector in (
    "section[itemprop=description]",
    "div.description",
    "description",
    "div.description-paragraph",
    "heading",
):
    print(f"{selector!r}: {len(soup.select(selector))} match(es)")

desc = soup.select_one("section[itemprop=description]") or soup.select_one("div.description")
if desc:
    print("\n--- first 25 children of description ---")
    for child in list(desc.find_all(recursive=True))[:25]:
        text = child.get_text(" ", strip=True)[:70]
        print(f"  <{child.name}> class={child.get('class')} num={child.get('num')} | {text}")

print("\n=== CLAIMS ===")
for selector in (
    "section[itemprop=claims]",
    "div.claims",
    "div.claim",
    "claim-text",
    "div.claim-text",
):
    print(f"{selector!r}: {len(soup.select(selector))} match(es)")

claim = soup.select_one("div.claim") or soup.select_one("claim")
if claim:
    print("\n--- first claim element ---")
    print(f"  <{claim.name}> num={claim.get('num')} | {claim.get_text(' ', strip=True)[:200]}")

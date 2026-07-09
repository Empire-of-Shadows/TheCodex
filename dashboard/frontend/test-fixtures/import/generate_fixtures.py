#!/usr/bin/env python3
"""
Generate malicious / edge-case test fixtures for the dashboard Builder's
"Import JSON" feature (dashboard/frontend/src/pages/BuilderPage.tsx `handleImport`).

Run:
    python generate_fixtures.py

Writes every fixture next to this script. Stdlib only. Re-runnable/idempotent.

Feed each file into the Builder's "Import JSON" button in the mode noted in
README.md and confirm the observed toast/behaviour matches the "Expected" column.

All payloads are BENIGN placeholders — standard `<script>alert(1)</script>` test
strings and inert comments. No working exploit, no real malware, no EICAR string.
"""

import gzip
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def write_json(name, obj):
    """Write a pretty-printed JSON fixture. ensure_ascii=False keeps RTL / zero-width
    / homoglyph code points as real bytes so the importer sees them verbatim."""
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"  wrote {name:32} ({os.path.getsize(path):>8,} bytes)")


def write_raw(name, data, *, binary=False):
    """Write a non-JSON / hostile-type fixture exactly as given."""
    path = os.path.join(HERE, name)
    mode = "wb" if binary else "w"
    if binary:
        with open(path, "wb") as f:
            f.write(data)
    else:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(data)
    print(f"  wrote {name:32} ({os.path.getsize(path):>8,} bytes)")


# ── Shared valid building blocks ─────────────────────────────────────────────
# A minimal top-level component and page/welcome that PASS validation, so fixtures
# that are meant to import successfully differ from the baseline only in the one
# hostile field under test.

def text(content):
    return {"type": "text", "content": content}


def page(label, content_text="Some body text.", **extra):
    p = {"label": label, "content": {"components": [text(content_text)]}}
    p.update(extra)
    return p


def guide(pages, **extra):
    d = {"pages": pages}
    d.update(extra)
    return d


def welcome(components, **extra):
    d = {"components": components}
    d.update(extra)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# A. Oversize fields
# ─────────────────────────────────────────────────────────────────────────────

def a_oversize():
    # 01 — page label 500 chars (cap is 100).
    write_json(
        "01-oversize-title-guide.json",
        guide([page("A" * 500)]),
    )

    # 02 — text content 5000 chars (cap is 4000).
    write_json(
        "02-oversize-content-guide.json",
        guide([page("Home", content_text="B" * 5000)]),
    )

    # 03 — welcome text content 5000 chars (cap is 4000).
    write_json(
        "03-oversize-component-welcome.json",
        welcome([text("C" * 5000)]),
    )

    # 04 — guide file padded past the 256 KB pre-parse size guard while staying
    # otherwise well-formed. Each page's content is a valid <=4000-char text, so
    # the size guard (not the validator) is what must fire first.
    big_pages = [page(f"Filler page {i}", content_text="x" * 4000) for i in range(80)]
    write_json("04-oversize-file-guide.json", guide(big_pages))

    # 05 — welcome file padded past the 64 KB welcome size guard.
    big_components = [text("y" * 4000) for _ in range(20)]
    write_json("05-oversize-file-welcome.json", welcome(big_components))


# ─────────────────────────────────────────────────────────────────────────────
# B. Deep nesting bombs
# ─────────────────────────────────────────────────────────────────────────────

def b_deep():
    # 06 — 100-level-deep children chain. normalizePages + addIdsToPage recurse
    # over `children` BEFORE validation, so this also exercises stack safety of
    # that pre-validation walk; the depth guard (max 5) must reject it.
    node = page("Leaf level 100")
    for depth in range(99, 0, -1):
        node = {"label": f"Level {depth}", "children": [node]}
    write_json("06-deep-children-100-guide.json", guide([node]))

    # 07 — a single page with 26 children (cap is 25 per node).
    kids = [page(f"Child {i}") for i in range(26)]
    write_json(
        "07-children-over-25-guide.json",
        guide([{"label": "Parent", "children": kids}]),
    )

    # 08 — a container component nested inside a container. Containers are not
    # allowed inside containers, so the validator must reject it.
    inner_container = {"type": "container", "components": [text("deep")]}
    outer_container = {"type": "container", "components": [inner_container]}
    write_json(
        "08-nested-container-guide.json",
        guide([{"label": "Home", "content": {"components": [outer_container]}}]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# C. Malicious JSON content
# ─────────────────────────────────────────────────────────────────────────────

def c_malicious():
    # 09 — guide whose text content carries XSS strings. Passes the structural
    # schema but is rejected by the content-safety scan (unsafe HTML/script markup).
    write_json(
        "09-xss-text-content-guide.json",
        guide([
            page("XSS body", content_text="<script>alert(document.cookie)</script>"),
            page("XSS img", content_text='<img src=x onerror=alert(1)>'),
            page("XSS svg", content_text='<svg/onload=alert(1)>'),
        ]),
    )

    # 10 — guide with HTML/JS inside labels (page + button label). Rejected by the
    # content-safety scan.
    write_json(
        "10-xss-labels-guide.json",
        guide([
            {
                "label": "<b>bold</b> <script>alert(1)</script>",
                "content": {
                    "components": [
                        text("normal body"),
                        {
                            "type": "action_row",
                            "buttons": [
                                {
                                    "style": "primary",
                                    "label": "<img src=x onerror=alert(2)>",
                                    "action": "role",
                                    "target": "123",
                                }
                            ],
                        },
                    ]
                },
            }
        ]),
    )

    # 11 — prototype-pollution attempt. Object.prototype.polluted must stay
    # undefined after import regardless of accept/reject.
    write_json(
        "11-prototype-pollution.json",
        {
            "__proto__": {"polluted": True},
            "constructor": {"prototype": {"polluted": True}},
            "pages": [
                {
                    "label": "Polluter",
                    "__proto__": {"polluted": True},
                    "content": {"components": [text("body")]},
                }
            ],
        },
    )

    # 12 — link button with a javascript: URL (only https:// is allowed).
    write_json(
        "12-javascript-url-link-button.json",
        guide([
            {
                "label": "Home",
                "content": {
                    "components": [
                        {
                            "type": "action_row",
                            "buttons": [
                                {
                                    "style": "link",
                                    "label": "Click me",
                                    "url": "javascript:alert(1)",
                                }
                            ],
                        }
                    ]
                },
            }
        ]),
    )

    # 13 — media_gallery item with a data: URL (only https:// is allowed).
    write_json(
        "13-data-url-media-guide.json",
        guide([
            {
                "label": "Home",
                "content": {
                    "components": [
                        {
                            "type": "media_gallery",
                            "items": [
                                {"media": "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=="}
                            ],
                        }
                    ]
                },
            }
        ]),
    )

    # 14 — guide with RTL override (U+202E), zero-width chars, and homoglyphs in
    # labels/content. Rejected by the content-safety scan on the invisible/bidi
    # control chars; the Cyrillic homoglyphs alone would be allowed.
    rtl = "‮piれＧＮＰ"          # RTL override + full-width homoglyphs
    zwsp = "he​llo​⁠world"  # zero-width space / word-joiner
    homoglyph = "Аdmіn Раnеl"        # Cyrillic look-alikes of "Admin Panel"
    write_json(
        "14-unicode-rtl-homoglyph-guide.json",
        guide([
            page(f"{rtl} {homoglyph}", content_text=f"{zwsp} — safe body {rtl}"),
        ]),
    )

    # 15 — two pages sharing the same id.
    write_json(
        "15-duplicate-ids-guide.json",
        guide([
            {"id": "dup", "label": "First", "content": {"components": [text("a")]}},
            {"id": "dup", "label": "Second", "content": {"components": [text("b")]}},
        ]),
    )

    # 16 — navigate button pointing at a page id that does not exist.
    write_json(
        "16-dangling-navigate-guide.json",
        guide([
            {
                "id": "home",
                "label": "Home",
                "content": {
                    "components": [
                        {
                            "type": "action_row",
                            "buttons": [
                                {
                                    "style": "primary",
                                    "label": "Go nowhere",
                                    "action": "navigate",
                                    "target": "does-not-exist",
                                }
                            ],
                        }
                    ]
                },
            }
        ]),
    )

    # 17 — accent_color integer out of range (valid 0..16777215).
    write_json(
        "17-accent-out-of-range-guide.json",
        guide([page("Home")], accent_color=99999999),
    )


# ─────────────────────────────────────────────────────────────────────────────
# D. Wrong / hostile file types (all reach the importer; must fail gracefully)
# ─────────────────────────────────────────────────────────────────────────────

def d_wrong_types():
    # 20 — HTML+JS body wearing a .json extension.
    write_raw(
        "20-html-polyglot.json",
        "<!doctype html><html><body><script>alert('xss')</script>"
        "<h1>totally a json file</h1></body></html>\n",
    )

    # 21 — empty file.
    write_raw("21-empty.json", "")

    # 22 — UTF-8 BOM + embedded null / control bytes; not valid JSON.
    write_raw(
        "22-not-json-bom-nulls.json",
        b"\xef\xbb\xbf{\x00\x01\x02 not really json \x7f}\n",
        binary=True,
    )

    # 23 — SVG carrying an inline script (benign). Image-looking upload.
    write_raw(
        "23-payload.svg",
        '<?xml version="1.0"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">\n'
        "  <script>alert('svg-xss')</script>\n"
        "  <rect width='1' height='1'/>\n"
        "</svg>\n",
    )

    # 24 — standalone HTML page.
    write_raw(
        "24-payload.html",
        "<!doctype html>\n<html><head><title>evil</title></head>\n"
        "<body onload=\"alert('html')\"><h1>not a guide</h1></body></html>\n",
    )

    # 25 — JavaScript payload text.
    write_raw(
        "25-evil.js",
        "// benign placeholder — represents a renamed .js upload\n"
        "(function(){ alert('js executed'); })();\n",
    )

    # 26 — inert placeholder resembling a PHP webshell (NO working code).
    write_raw(
        "26-webshell.php",
        "<?php\n"
        "// BENIGN PLACEHOLDER — not a functional webshell.\n"
        "// Represents the shape of a malicious .php upload for import testing.\n"
        "// (intentionally does nothing)\n"
        "?>\n",
    )

    # 27 — double extension with a fake PE/MZ header; represents a renamed binary.
    write_raw(
        "27-fake-double-ext.json.exe",
        b"MZ\x90\x00\x03\x00\x00\x00"  # DOS MZ header
        b"BENIGN PLACEHOLDER - not a real executable\n",
        binary=True,
    )

    # 28 — a real gzip stream whose decompressed bytes are non-JSON. Tests that the
    # importer does NOT auto-decompress; reading raw bytes as text fails to parse.
    inner = b"this is not json, and the importer must not gunzip it\n"
    write_raw("28-decompression-bomb.json.gz", gzip.compress(inner), binary=True)


def main():
    print(f"Generating import fixtures in {HERE}\n")
    a_oversize()
    b_deep()
    c_malicious()
    d_wrong_types()
    print("\nDone.")


if __name__ == "__main__":
    main()

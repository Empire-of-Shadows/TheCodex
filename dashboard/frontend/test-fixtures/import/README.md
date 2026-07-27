# Import feature — malicious / edge-case test fixtures

Hand-feedable test files for the Builder's **Import JSON** button
(`dashboard/frontend/src/pages/BuilderPage.tsx` → `handleImport`).

Each file targets one guard rail on the untrusted-import path:
**size guard → `JSON.parse` → shape check → schema validator → render**.

> **Safety:** every "malicious" payload here is a **benign placeholder** — standard
> `<script>alert(1)</script>` test strings and inert comments. Nothing is a working
> exploit, real malware, or an EICAR string.

## How to use

1. Run the dashboard and open a guild's **Builder**.
2. Pick the **mode** from the table below (`guide` vs `greeting`) — the byte limit and
   validator differ per mode. Mode = whichever editor (guide or greeting) is active.
3. Click **Import JSON** and select the fixture. The `<input accept=".json">` filter
   only narrows the OS picker, so to test the wrong-type files (group D) either type the
   name into the picker or drag the file in.
4. Confirm the toast / behaviour matches the **Expected** column.

> **Note:** fixtures 09, 10, 11, and 14 used to import successfully; the importer now
> rejects them (see the content-safety scan in `src/validators/safeContent.ts` and its
> backend mirror `utils/safe_content.py`). The table below reflects the current behaviour.

## Regenerating

```bash
python generate_fixtures.py
```

Stdlib only; re-runnable. Several files must be large or contain control characters, so
they are generated rather than hand-authored. The generated files are committed so the
directory is usable without running the script.

The guide/greeting JSON fixtures below (01–17, 20–22) were verified by running them through
the app's own `validateGuideSchema` / `validateGreetingSchema`; the **Expected** messages
are the validators' actual output.

## Fixtures

### A. Oversize fields
| File | Mode | Expected result | Verifies |
|------|------|-----------------|----------|
| `01-oversize-title-guide.json` | guide | Rejected — *"label exceeds 100 characters."* | Page-title length cap (100) |
| `02-oversize-content-guide.json` | guide | Rejected — *"content exceeds 4000 characters."* | Text-body length cap (4000) |
| `03-oversize-component-greeting.json` | greeting | Rejected — *"content exceeds 4000 characters."* | Greeting-mode field cap |
| `04-oversize-file-guide.json` | guide | Rejected — *"File is too large (max 256 KB…)"* **before** parsing | Guide 256 KB size guard (file is ~327 KB) |
| `05-oversize-file-greeting.json` | greeting | Rejected — *"File is too large (max 64 KB…)"* **before** parsing | Greeting 64 KB size guard (file is ~79 KB) |

### B. Deep nesting bombs
| File | Mode | Expected result | Verifies |
|------|------|-----------------|----------|
| `06-deep-children-100-guide.json` | guide | Rejected — *"…page nesting exceeds maximum depth of 5."* | Depth cap; also that `normalizePages`/`addIdsToPage` recurse this tree **before** validation without crashing |
| `07-children-over-25-guide.json` | guide | Rejected — *"children has 26 items; max is 25."* | Per-node child fan-out cap (25) |
| `08-nested-container-guide.json` | guide | Rejected — *'type "container" is invalid inside a container.'* | Component nesting is not recursive |

### C. Malicious JSON content
| File | Mode | Expected result | Verifies |
|------|------|-----------------|----------|
| `09-xss-text-content-guide.json` | guide | Rejected — *"…content contains disallowed HTML or script markup."* | `<script>` / `<img onerror>` / `<svg onload>` in body is blocked on input |
| `10-xss-labels-guide.json` | guide | Rejected — *"…label contains disallowed HTML or script markup."* | HTML/JS in page + button **labels** is blocked |
| `11-prototype-pollution.json` | guide | Rejected — *'…contains a disallowed property name "__proto__".'* (backend: *"Unknown top-level field(s)…"*) | `__proto__` / `constructor` / `prototype` keys rejected anywhere in the tree; `Object.prototype` stays clean |
| `12-javascript-url-link-button.json` | guide | Rejected — *"url … must start with https://."* | Link-button URL scheme allowlist (structural error keeps priority over the content scan) |
| `13-data-url-media-guide.json` | guide | Rejected — *"media must be an https:// URL."* | Media URL scheme allowlist |
| `14-unicode-rtl-homoglyph-guide.json` | guide | Rejected — *"…contains a disallowed invisible or bidirectional control character."* | RTL override (U+202E) + zero-width chars blocked; **homoglyphs / non-Latin scripts stay allowed** (only the invisible controls trigger it) |
| `15-duplicate-ids-guide.json` | guide | Rejected — *'id "dup" is duplicated.'* | Page-id uniqueness |
| `16-dangling-navigate-guide.json` | guide | Rejected — *'…targets page "does-not-exist" which does not exist.'* | Navigate-target referential integrity |
| `17-accent-out-of-range-guide.json` | guide | Rejected — *"accent_color integer 99999999 is out of range (0–16777215)."* | Accent-colour bounds |

### D. Wrong / hostile file types
All reach the importer (the `.json` filter is bypassable). They must fail **gracefully** and
never execute or render.

Two gates apply here: a **filename check** (`.json` only) rejects the wrong-extension files
up front, and files that *are* named `.json` but aren't valid JSON fail at parse.

| File | Mode | Expected result | Verifies |
|------|------|-----------------|----------|
| `20-html-polyglot.json` | guide | Rejected — *"Failed to parse JSON file"* | HTML+`<script>` wearing a `.json` name is rejected, not rendered |
| `21-empty.json` | guide | Rejected — *"Failed to parse JSON file"* | Empty file handled |
| `22-not-json-bom-nulls.json` | guide | Rejected — *"Failed to parse JSON file"* | BOM + embedded null/control bytes handled |
| `23-payload.svg` | either | Rejected — *"Only .json files can be imported."* | Image-looking SVG-with-`<script>` upload blocked by extension gate |
| `24-payload.html` | either | Rejected — *"Only .json files can be imported."* | Standalone HTML page blocked by extension gate |
| `25-evil.js` | either | Rejected — *"Only .json files can be imported."* | Renamed `.js` upload blocked by extension gate |
| `26-webshell.php` | either | Rejected — *"Only .json files can be imported."* | `.php` upload (inert placeholder) blocked by extension gate |
| `27-fake-double-ext.json.exe` | either | Rejected — *"Only .json files can be imported."* | Double extension: `.exe` is the real one → blocked |
| `28-decompression-bomb.json.gz` | either | Rejected — *"Only .json files can be imported."* | `.gz` blocked by extension gate; importer never gunzips |

# Welcome Builder - Schema Reference

## Top-level object

| Field | Type | Required | Description |
|---|---|---|---|
| `accent_color` | string or integer | No | Left-side accent bar color |
| `components` | array | **Yes** | Layout components, 1-10 items |

### `accent_color`

- **Hex string:** `"#RRGGBB"` (e.g. `"#5865F2"`)
- **Integer:** `0`-`16777215` (e.g. `5793266`)

---

## Component types

Each item in `components` is an object with a `"type"` field.

Valid top-level types: `separator`, `text`, `section`, `action_row`, `container`, `media_gallery`, `file`

### `separator`

Draws a horizontal divider. No other fields.

```json
{"type": "separator"}
```

---

### `text`

A standalone text display block.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `type` | `"text"` | Yes | - |
| `content` | string | **Yes** | 1-4000 characters; supports markdown; placeholders resolved |

```json
{"type": "text", "content": "Welcome, {member}!"}
```

---

### `section`

A row with 1-3 text objects on the left and a required accessory on the right.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `type` | `"section"` | Yes | - |
| `content` | array of text objects | **Yes** | 1-3 items; each must be `{"type": "text", "content": "..."}` |
| `accessory` | thumbnail or button object | **Yes** | - |

#### Thumbnail accessory

| Field | Type | Required | Constraints |
|---|---|---|---|
| `type` | `"thumbnail"` | Yes | - |
| `media` | string | **Yes** | `"member_avatar"` (resolved at render time) or any `https://` URL |
| `description` | string | No | Alt text for the image |

#### Button accessory (in a section)

Same structure as a regular button (see below). Link buttons and non-link buttons are both valid.

---

### `action_row`

A row containing either buttons **or** a select menu (mutually exclusive).

| Field | Type | Required | Constraints |
|---|---|---|---|
| `type` | `"action_row"` | Yes | - |
| `buttons` | array of button objects | **One required** | 1-5 items |
| `select` | string_select object | **One required** | A single select menu |

You must provide exactly one of `buttons` or `select`, not both.

---

### `container`

Groups multiple components inside a styled box. Containers **cannot** be nested.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `type` | `"container"` | Yes | - |
| `components` | array | **Yes** | 1-10 child components |
| `accent_color` | string or integer | No | Same format as top-level `accent_color` |
| `spoiler` | boolean | No | Defaults to `false` |

Allowed child types: `separator`, `text`, `section`, `action_row`, `media_gallery`, `file`

```json
{
  "type": "container",
  "accent_color": "#57F287",
  "components": [
    {"type": "text", "content": "Inside a container!"},
    {"type": "separator"}
  ]
}
```

---

### `media_gallery`

Displays 1-10 media items in a gallery layout.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `type` | `"media_gallery"` | Yes | - |
| `items` | array | **Yes** | 1-10 items |

Each item:

| Field | Type | Required | Constraints |
|---|---|---|---|
| `media` | string | **Yes** | Must be an `https://` URL |
| `description` | string | No | Max 256 characters |
| `spoiler` | boolean | No | Defaults to `false` |

```json
{
  "type": "media_gallery",
  "items": [
    {"media": "https://example.com/banner.png", "description": "Server banner"}
  ]
}
```

---

### `file`

Displays a single media file.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `type` | `"file"` | Yes | - |
| `media` | string | **Yes** | Must be an `https://` URL |
| `spoiler` | boolean | No | Defaults to `false` |

```json
{"type": "file", "media": "https://example.com/welcome.png"}
```

---

## Button object

Used inside `action_row.buttons` and as a `section.accessory`.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `type` | `"button"` | (implied) | Only required when used as section accessory |
| `style` | string | **Yes** | `"primary"`, `"secondary"`, `"success"`, `"danger"`, `"link"` |
| `label` | string | **Yes** | 1-80 characters; placeholders resolved |
| `emoji` | string | No | Unicode emoji or Discord emoji string |
| `disabled` | boolean | No | Defaults to `false` |
| `url` | string | Link buttons only | Must start with `https://` |
| `action` | string | Non-link buttons only | Must be a valid action name (see Actions Reference) |

**Rules:**
- `"link"` style buttons require `url` and must **not** have `action`
- All other styles require `action` and must **not** have `url`
- The old `custom_id` field is no longer accepted - use `action` instead

---

## String select object

Used inside `action_row.select`.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `placeholder` | string | No | Max 150 characters |
| `options` | array | **Yes** | 1-25 option objects |
| `min_values` | integer | No | 1-25, defaults to 1 |
| `max_values` | integer | No | 1-25, defaults to 1 |

### Select option

| Field | Type | Required | Constraints |
|---|---|---|---|
| `label` | string | **Yes** | 1-100 characters; placeholders resolved |
| `action` | string | **Yes** | Must be a valid action name |
| `description` | string | No | Max 100 characters |
| `emoji` | string | No | Unicode or Discord emoji |

---

## Actions Reference

Non-link buttons and select options use named actions instead of raw `custom_id` strings.

| Action | Description |
|---|---|
| `open_guide` | Opens the server guide menu |
| `server_info` | Shows server statistics |
| `channel_list` | Shows channel overview |
| `getting_started` | Shows getting started tips |
| `suggest` | Opens the suggestion submission form |
| `browse_drops` | Browse available free gaming drops |
| `server_rules` | Shows link to server rules channel |
| `role_info` | Shows server roles overview |

---

## Placeholders

Text content and button labels support placeholder substitution at render time.

| Placeholder | Description |
|---|---|
| `{member}` | Member mention (clickable `@user`) |
| `{member_name}` | Member's display name (plain text) |
| `{member_count}` | Guild member number at time of join |
| `{guild_name}` | Server name |
| `{voice_active}` | Number of active voice channels |
| `{random_greeting}` | A random themed greeting message with the member mentioned |

---

## Validation constraints summary

| Constraint | Limit |
|---|---|
| Total components | 1-10 |
| `text.content` length | 1-4000 characters |
| `section.content` items | 1-3 |
| `action_row.buttons` items | 1-5 |
| `action_row.select.options` items | 1-25 |
| `button.label` length | 1-80 characters |
| `select option.label` length | 1-100 characters |
| `select.placeholder` length | 1-150 characters |
| `container.components` items | 1-10 |
| `media_gallery.items` items | 1-10 |
| `media_gallery item.description` length | 1-256 characters |
| `accent_color` integer range | 0-16777215 |

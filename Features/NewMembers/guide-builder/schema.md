# Guide Builder - Schema Reference

## Top-level object

| Field | Type | Required | Description |
|---|---|---|---|
| `accent_color` | string or integer | No | Left-side accent bar color |
| `pages` | array | **Yes** | Page tree, 1+ page objects |

### `accent_color`

- **Hex string:** `"#RRGGBB"` (e.g. `"#4D0EB3"`)
- **Integer:** `0`-`16777215` (e.g. `5046963`)

---

## Page object

Each item in `pages` (and in `children`) is a page object.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `id` | string | No | Auto-generated from label if omitted (slugified). Must be unique across entire guide. Max 100 chars. |
| `label` | string | **Yes** | Display name in dropdowns and breadcrumbs. 1-100 characters. |
| `description` | string | No | For search indexing and dropdown descriptions. Max 100 characters. |
| `icon` | string | No | Emoji shown in dropdown options. |
| `order` | integer | No | Sort order within siblings. Defaults to array position. |
| `content` | object | No* | Components V2 layout (see Content Components below). |
| `children` | array | No* | Sub-pages (same page schema, recursive). Max 25 per level. |

*A page must have at least `content`, `children`, or both.

### Page behavior

- **content + children** → Shows content AND a dropdown to navigate children
- **children only** → Shows title/description header + dropdown
- **content only** → Leaf page, no dropdown

### `content` object

| Field | Type | Required | Constraints |
|---|---|---|---|
| `components` | array | No | 1-10 component objects (see Component types below) |

---

## Component types

Each item in `content.components` is an object with a `"type"` field.

Valid types: `separator`, `text`, `section`, `action_row`, `container`, `media_gallery`

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
{"type": "text", "content": "# Welcome to {guild_name}!"}
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
| `media` | string | **Yes** | Must be `"member_avatar"` (resolved to viewer's avatar at render time). External URLs are not supported - use a single-item `media_gallery` for external images. |
| `description` | string | No | Alt text for the image |

#### Button accessory (in a section)

Same structure as a regular button (see Button object below). Both link and navigate buttons are valid.

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

Allowed child types: `separator`, `text`, `section`, `action_row`, `media_gallery`

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
| `action` | string | Non-link buttons only | Must be `"navigate"` |
| `target` | string | Navigate buttons only | Must be a valid page `id` in the guide |

**Rules:**
- `"link"` style buttons require `url` and must **not** have `action`/`target`
- All other styles require `action` set to `"navigate"` and a `target` page ID
- Guide buttons only support the `"navigate"` action - no other actions are valid

### Navigate button example

```json
{
  "style": "primary",
  "label": "View Rules",
  "action": "navigate",
  "target": "rules"
}
```

The `target` must match a page `id` somewhere in the guide. If the target page doesn't exist, validation fails.

### Link button example

```json
{
  "style": "link",
  "label": "Website",
  "url": "https://example.com"
}
```

---

## String select object

Used inside `action_row.select`. In guide context, all select options must use the `"navigate"` action.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `placeholder` | string | No | Max 150 characters |
| `options` | array | **Yes** | 1-25 option objects |
| `min_values` | integer | No | 1-25, defaults to 1 |
| `max_values` | integer | No | 1-25, defaults to 1 |

### Select option (guide)

| Field | Type | Required | Constraints |
|---|---|---|---|
| `label` | string | **Yes** | 1-100 characters |
| `action` | string | **Yes** | Must be `"navigate"` |
| `target` | string | **Yes** | Must be a valid page `id` in the guide |
| `description` | string | No | Max 100 characters |
| `emoji` | string | No | Unicode or Discord emoji |

```json
{
  "type": "action_row",
  "select": {
    "placeholder": "Choose a topic...",
    "options": [
      {"label": "Rules", "action": "navigate", "target": "rules", "emoji": "📜"},
      {"label": "Channels", "action": "navigate", "target": "channels", "emoji": "📺"}
    ]
  }
}
```

---

## Actions reference

Guide buttons and select options only support the `"navigate"` action. This is different from the welcome builder, which has a registry of named actions.

| Action | Description |
|---|---|
| `navigate` | Jump to another page in the guide. Requires `target` set to a valid page `id`. |

Link buttons use `url` instead of `action` and navigate to external URLs.

---

## Placeholders

Text content and button labels support placeholder substitution at render time.

| Placeholder | Description |
|---|---|
| `{member}` | Viewer's Discord mention (clickable `@user`) |
| `{member_name}` | Viewer's display name (plain text) |
| `{member_count}` | Guild member count at time of viewing |
| `{guild_name}` | Server name |
| `{voice_active}` | Number of active voice channels |
| `{random_greeting}` | A random themed greeting message with the viewer mentioned |

See [`placeholders.md`](placeholders.md) for full details.

---

## Validation constraints summary

| Constraint | Limit |
|---|---|
| `pages` array | 1+ items (non-empty) |
| Page nesting depth | Max 5 levels |
| `children` per page | Max 25 |
| `content.components` items | 1-10 |
| `text.content` length | 1-4000 characters |
| `page.label` length | 1-100 characters |
| `page.description` length | 1-100 characters |
| `page.id` length | 1-100 characters |
| Page IDs | Must be unique across entire guide |
| Navigate targets | Must reference existing page IDs |
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
| Non-link button action | Must be `"navigate"` |
| Select option action | Must be `"navigate"` |

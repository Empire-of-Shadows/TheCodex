# Board Builder - Schema Reference

Everything you can put in an info board, what each part does, and the limits Discord
enforces.

## Shape

A board is two things: the message people see, and the pool of private responses its
buttons reveal.

```json
{
  "accent_color": "#4D0EB3",
  "components": [ ... ],
  "responses": [
    { "id": "rules", "label": "Server Rules", "components": [ ... ] }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `accent_color` | no | `#RRGGBB` or an integer. The stripe down the left edge. |
| `components` | yes | The board message. Up to **10** blocks. |
| `responses` | no | Up to **25** private replies. |

The whole file must stay under **128 KB**.

## Responses

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Lowercase letters, digits, `-` and `_`. Must start with a letter or digit. Max 48 characters. Unique within the board. |
| `label` | no | What the builder's sidebar shows. Max 100 characters. Members never see it. |
| `accent_color` | no | Defaults to the board's, so everything reads as one thing. |
| `components` | yes | Up to **10** blocks, same rules as the board message. |

A response is a full layout, so it can carry its own buttons - including buttons
pointing at other responses.

## Blocks

Both the board message and each response accept the same blocks:

| Type | What it is |
|---|---|
| `text` | Markdown. Up to 4000 characters. |
| `separator` | A thin dividing line. |
| `section` | 1-3 text blocks with a thumbnail or button on the right. |
| `action_row` | Either up to 5 buttons **or** one dropdown - never both. |
| `container` | A boxed group with its own accent colour. Up to 10 child blocks. |
| `media_gallery` | Up to 10 images by `https://` URL. |

`container` cannot be nested inside a `container`.

## What a board button can do

Every non-link button needs an `action` and a `target`.

| Action | Target | What happens |
|---|---|---|
| `reply` | a response `id` | Sends that response privately to whoever clicked. |
| `channel` | a channel ID | Replies privately with a link to that channel. |
| `role` | a role ID | Gives the role, or takes it away if they already have it. |

Link buttons are different: they take a `url` starting with `https://` and must
**not** have `action` or `target`.

```json
{
  "type": "action_row",
  "buttons": [
    { "type": "button", "style": "primary",   "label": "Server Rules", "action": "reply",   "target": "rules" },
    { "type": "button", "style": "secondary", "label": "Get Gamer",    "action": "role",    "target": "123456789012345678" },
    { "type": "button", "style": "secondary", "label": "Say hi",       "action": "channel", "target": "234567890123456789" },
    { "type": "button", "style": "link",      "label": "Website",      "url": "https://eosofficial.club" }
  ]
}
```

Styles: `primary`, `secondary`, `success`, `danger`, `link`. Labels max 80 characters.

## Dropdowns

An `action_row` with a `select` instead of `buttons`. Options take the same
`action` / `target` pair.

```json
{
  "type": "action_row",
  "select": {
    "placeholder": "Looking for something else?",
    "options": [
      { "label": "How roles work", "description": "Earning and picking roles", "action": "reply", "target": "roles" },
      { "label": "Head to general", "action": "channel", "target": "234567890123456789" }
    ]
  }
}
```

Up to 25 options. Labels and descriptions max 100 characters each. Placeholder max 150.

## Placeholders

| Placeholder | Where it works | Becomes |
|---|---|---|
| `{guild_name}` | anywhere | Your server's name |
| `{member}` | private responses only | A mention of whoever clicked |
| `{member_name}` | private responses only | Their display name |

On the board message itself there is nobody to substitute, so `{member}` and
`{member_name}` come out empty. Member counts are deliberately not available: the
board is posted once and edited rarely, so a live-looking number would be wrong
almost immediately.

## Common errors

- **"points at response X, which does not exist"** - a button targets a response
  you renamed or deleted. Fix the button or re-add the response.
- **"target for the channel action must be a Discord ID"** - use the numeric ID,
  not `#channel-name`. The builder's dropdown fills this in for you.
- **"link buttons must not have action"** - a button is both a link and an action.
  Pick one.
- **"cannot have both buttons and select"** - split them into two action rows.

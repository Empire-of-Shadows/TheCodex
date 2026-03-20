# Guide Builder — Placeholder Reference

Placeholders are substituted at render time (when the member views the guide). They are case-sensitive and must appear exactly as shown, including the curly braces.

## Available placeholders

| Placeholder | Replaced with | Example output |
|---|---|---|
| `{member}` | Discord mention of the viewer | `<@123456789>` |
| `{member_name}` | Viewer's display name | `CoolGamer42` |
| `{member_count}` | Human member count (excludes bots) | `1234` |
| `{guild_name}` | Server name | `Empire of Shadows` |
| `{voice_active}` | Number of currently active voice channels | `3` |
| `{random_greeting}` | Random themed greeting with viewer mention | `Achievement unlocked: <@123456789> joined the server! 🏆` |

## Where placeholders are substituted

| Location | Supported |
|---|---|
| `text.content` | Yes |
| `section.content[].content` (text objects inside sections) | Yes |
| `button.label` | Yes |
| `thumbnail.description` | No — not substituted |
| `thumbnail.media` URL | No — only `"member_avatar"` is a special token |
| `page.label` | No — labels are static |
| `page.description` | No — descriptions are static |

## Notes

- `{member}` refers to the **viewer** of the guide, not a joining member. In guide context, anyone can open the guide at any time.
- `{voice_active}` is `"0"` if analytics are unavailable.
- `{member_count}` reflects the human member count at the moment the guide is viewed, excluding bots.
- `{random_greeting}` picks from 100+ themed messages (gaming, food, space, music, etc.) and always includes the viewer's mention. Each view gets a different greeting.

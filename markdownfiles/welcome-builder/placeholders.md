# Welcome Builder — Placeholder Reference

Placeholders are substituted at render time (when the member joins). They are case-sensitive and must appear exactly as shown, including the curly braces.

## Available placeholders

| Placeholder | Replaced with | Example output |
|---|---|---|
| `{member}` | Discord mention | `<@123456789>` |
| `{member_name}` | Member's display name | `CoolGamer42` |
| `{member_count}` | Human member count at join time | `1234` |
| `{guild_name}` | Server name | `Empire of Shadows` |
| `{voice_active}` | Number of currently active voice channels | `3` |
| `{random_greeting}` | Random themed greeting with member mention | `Achievement unlocked: <@123456789> joined the server! 🏆` |

## Where placeholders are substituted

| Location | Supported |
|---|---|
| `text.content` | Yes |
| `section.content[].content` (text objects inside sections) | Yes |
| `button.label` | Yes |
| `thumbnail.description` | No — not substituted |
| `thumbnail.media` URL | No — only `"member_avatar"` is a special token |

## Notes

- `{member}` produces a Discord mention (`<@id>`), so the member gets pinged in the welcome message if used in a text block.
- `{voice_active}` is `"0"` if analytics are unavailable.
- `{member_count}` reflects the human member count at the moment of the join event, excluding bots.
- `{random_greeting}` picks from 100+ themed messages (gaming, food, space, music, etc.) and always includes the member mention. Each join gets a different greeting.

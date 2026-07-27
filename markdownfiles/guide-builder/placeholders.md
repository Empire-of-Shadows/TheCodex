# Guide Builder - Placeholders

Placeholders are short words in curly braces that the bot swaps out for real
information when somebody opens the guide. Type them into your text exactly as
shown, braces included, and they fill themselves in.

They are case sensitive. `{member_name}` works, `{Member_Name}` does not and will
just sit there as literal text.

## The list

| Type this | And the member sees |
|---|---|
| `{member}` | A mention of whoever is reading, like @CoolGamer42 |
| `{member_name}` | Their display name as plain text, like CoolGamer42 |
| `{member_count}` | How many real members the server has right now, bots excluded |
| `{guild_name}` | Your server's name |
| `{voice_active}` | How many voice channels currently have somebody in them |
| `{random_greeting}` | A different themed greeting each time, which includes a mention of the reader |

In the guide, "member" always means **the person reading the page right now**, not
somebody who just joined. Anyone can open the guide at any time.

## Where they work

| Place | Works? |
|---|---|
| Text blocks | Yes |
| Text inside a section | Yes |
| Button labels | Yes |
| Dropdown prompt text | Yes |
| Dropdown option labels and descriptions | Yes |
| Page names and page descriptions | No, these stay exactly as you type them |
| Image alt text | No |

## Things worth knowing

- **`{member}` pings.** It creates a real mention. That is nice once at the top of
  a page and annoying five times down it.
- **`{member_name}` does not ping.** Use it when you want to greet somebody
  without notifying them.
- **`{voice_active}` shows 0** if the bot cannot read voice activity at that
  moment. It is a fun detail, not something to build a sentence around.
- **`{random_greeting}` already includes a mention** of the reader, so you do not
  need to add `{member}` next to it.
- Preview mode fills placeholders with sample values, so you can see how long the
  finished line actually is.

## Example

Typed into a text block:

```
# Welcome to {guild_name}
Hey {member_name}, glad you found us. There are {member_count} of us here,
and {voice_active} voice channels are busy right now.
```

What a reader sees:

> **Welcome to Empire of Shadows**
> Hey CoolGamer42, glad you found us. There are 1,204 of us here,
> and 3 voice channels are busy right now.

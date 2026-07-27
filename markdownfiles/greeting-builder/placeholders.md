# Greeting Builder - Placeholders

Placeholders are short words in curly braces that the bot swaps out for real
information about the person who just joined. Type them into your text exactly as
shown, braces included, and they fill themselves in.

They are case sensitive. `{member_name}` works, `{Member_Name}` does not and will
just sit there as literal text.

## The list

| Type this | And the message shows |
|---|---|
| `{member}` | A mention of the new member, like @CoolGamer42 |
| `{member_name}` | Their display name as plain text, like CoolGamer42 |
| `{member_count}` | Their member number, counting real members only, bots excluded |
| `{guild_name}` | Your server's name |
| `{voice_active}` | How many voice channels had somebody in them at that moment |
| `{random_greeting}` | A different themed greeting every join, which includes a mention of the new member |

## Where they work

| Place | Works? |
|---|---|
| Text blocks | Yes |
| Text inside a section | Yes |
| Button labels | Yes |
| Dropdown option labels | Yes |
| Dropdown prompt text and option descriptions | No, these stay exactly as you type them |
| Image alt text | No |

## Things worth knowing

- **`{member}` pings.** It is what actually notifies the new person that they have
  been welcomed. Use it once, near the top.
- **`{member_name}` does not ping.** Good for the rest of the message.
- **`{member_count}` is their number**, as in "you are member #1204". It counts
  people, not bots.
- **`{voice_active}` shows 0** if the bot cannot read voice activity at that
  moment. It is a nice touch, not something to build a sentence around.
- **`{random_greeting}` already includes a mention** of the new member, so you do
  not need to add `{member}` next to it. It pulls from a large pool of themed
  one-liners, so the greeting channel does not read the same every time.
- Preview mode fills placeholders with sample values, so you can see how long the
  finished line actually is.

## Example

Typed into a section:

```
# Welcome to {guild_name}, {member}!
-# You are member #{member_count}

Say hi in chat when you get a minute. {voice_active} voice channels are
busy right now if you would rather just jump in.
```

What the channel shows:

> **Welcome to Empire of Shadows, @CoolGamer42!**
> You are member #1204
>
> Say hi in chat when you get a minute. 3 voice channels are busy right now if
> you would rather just jump in.

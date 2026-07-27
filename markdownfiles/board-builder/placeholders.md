# Board Builder - Placeholders

Placeholders are little tokens you type into any text block. The bot swaps them for
real values when it sends the message.

Boards have fewer of them than the greeting, on purpose - see *Why so few* below.

## The list

- **`{guild_name}`**
  Your server's name. Works everywhere: the board message and every private response.

- **`{member}`**
  A mention of the person who clicked, like @CoolGamer42. Works **only inside a
  private response** - the board message has nobody to mention.

- **`{member_name}`**
  Their display name as plain text, no mention or ping. Same rule: private responses
  only.

## Example

In a response:

```
# Hey {member}, welcome to {guild_name}!

Here's everything you need to get going.
```

Which arrives as:

> **Hey @CoolGamer42, welcome to Empire of Shadows!**
>
> Here's everything you need to get going.

On the board message itself, write for everyone at once:

```
# Welcome to {guild_name}
Tap a button below and I'll send you the details privately.
```

## Why so few

The greeting has `{member_count}`, `{voice_active}` and `{random_greeting}` because
it is written fresh every time someone joins - the numbers are correct at the moment
they are sent.

A board is posted once and edited only when you change it. A member count baked into
it would be wrong within the hour and stay wrong, which reads worse than not showing
one at all. If you want live numbers, put them in the greeting or a command.

## Notes

- Type them exactly as shown, including the curly braces. `{Member}` will not work.
- A placeholder that does not apply comes out as empty text rather than breaking the
  message, so a `{member}` left on the board message just disappears.
- Placeholders work in button and option labels too, not just text blocks.

# Welcome Builder - Schema Reference

Everything you can put in a welcome message, what each part does, and the limits
Discord and the bot enforce. You do not have to write any of this by hand - the
builder does it for you - but this is the page to check when something will not
save.

## The message

A welcome message is a single list of blocks, up to **10** of them, plus an accent
color. There are no pages here - that is the guide builder.

The whole design can be up to 64 KB, which is far more text than anybody should
put in a welcome message.

## Blocks

These are the six things you can drag onto the canvas.

### Text

Plain text with Discord formatting. Up to **4000 characters**.

Formatting that works: `**bold**`, `*italic*`, `__underline__`, `~~strikethrough~~`,
`# Heading`, `## Smaller heading`, `- bullet`, `> quote`, `` `code` ``, `-# small
grey text`, links, custom emoji, `<#channel>` and `<@role>` mentions.

### Separator

A thin dividing line. No settings, it just breaks things up.

### Section

Text with something attached on the right side. This is how you get the new
member's avatar next to your greeting.

- **1 to 3 text blocks** on the left.
- **One attachment** on the right, and it is required. Pick either:
  - **Thumbnail** - shows the new member's avatar. This is the only thing a
    thumbnail can show; it cannot display a picture from a URL. Use a Media
    Gallery for that.
  - **Button** - a normal button, same options as below.

### Action Row

A row of controls. It holds **either buttons or one dropdown**, never both.

- **Buttons:** 1 to 5 in a row.
- **Dropdown:** one per row.

### Container

A box with its own colored stripe that groups other blocks together.

- Holds **1 to 10** blocks: text, separators, sections, action rows, and media
  galleries.
- **Containers cannot go inside containers.**
- Has its own accent color, which overrides the message-wide one for that box.
- Can be marked as a spoiler, so the whole box is hidden until clicked.

### Media Gallery

A grid of images, good for a server banner.

- **1 to 10 images.**
- Every image needs an `https://` address. Direct image links only - a link to a
  page that contains an image will not work.
- Each image can have alt text up to 256 characters, and can be marked as a
  spoiler.

## Buttons

| Field | What it is | Limits |
|---|---|---|
| Label | The text on the button | Required, up to 80 characters |
| Style | Blurple, grey, green, red, or link | Required |
| Emoji | Shown before the label | Optional |
| Action | What happens on click | Required unless it is a link button |

### What a welcome button can do

Pick one of these from the dropdown. Everything a member sees from these buttons
is private to them, so clicking around does not spam your welcome channel.

| Action | What the member gets |
|---|---|
| Opens the server guide menu | Your guide, the one built in the Guide tab |
| Shows server statistics | Member count, creation date, channel and role counts, boost level |
| Shows channel overview | A summary of your categories and channels |
| Shows getting started tips | A short how-to-use-this-server card |
| Opens the suggestion submission form | The `/suggest` form |
| Browse available free gaming drops | Current Prime Gaming and free game offers |
| Shows link to server rules channel | A pointer to the channel with "rules" in the name |
| Shows server roles overview | Your roles and how many members each has |

Two of these depend on your setup: **Opens the server guide menu** needs a guide
built in the Guide tab, and **Shows link to server rules channel** needs a channel
with "rules" in its name. If either is missing, the member gets a polite "not
available" note instead.

Link buttons are the odd one out: they open a URL and never trigger anything in
the bot, so they have no action. The address must start with `https://`.

## Dropdowns

| Field | What it is | Limits |
|---|---|---|
| Placeholder | Grey text shown before a choice is made | Up to 150 characters |
| Options | The choices | 1 to 25 |

Each option has:

| Field | Limits |
|---|---|
| Label | Required, up to 100 characters |
| Description | Optional, up to 100 characters |
| Emoji | Optional |
| Action | Required - the same list of actions as buttons above |

A dropdown is a tidy way to offer six things without six buttons.

## Colors

The accent color is the vertical stripe on the left of the message. Set it in the
top bar for the whole message, or per container. Any hex color works, for example
`#5865F2`.

## What is not allowed

Every save is scanned for content that has no business in a Discord message:

- HTML and script markup, for example `<script>`, `<iframe>`, `<img onerror=...>`.
- `javascript:` links.
- Invisible and text-direction characters, which can be used to make a message
  read differently than it actually is.

Normal text, emoji, Discord mentions, and non-English scripts are all fine. If you
see a "disallowed markup" error, it is almost always text pasted in from a website.

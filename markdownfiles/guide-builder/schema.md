# Guide Builder - Schema Reference

Everything you can put in a guide, what each part does, and the limits Discord and
the bot enforce. You do not have to write any of this by hand - the builder does
it for you - but this is the page to check when something will not save.

## Pages

A guide is a list of pages. Every page needs a **name**, and it needs either some
**content**, some **pages inside it**, or both. A page with neither is what
triggers "must have content, children, or both".

| Field | What it is | Limits |
|---|---|---|
| Name (label) | What members see in menus and breadcrumbs | Required, up to 100 characters |
| Description | One line of helper text under the name in dropdowns | Up to 100 characters |
| Icon | An emoji shown next to the name | Optional |
| ID | Used internally so buttons can point at this page | Created from the name automatically, must be unique |
| Content | The blocks shown when the page opens | Up to 10 blocks |
| Pages inside | Child pages, which get their own dropdown | Up to 25 per page |

Other rules:

- **Nesting goes 5 levels deep.** Deeper than that and the guide gets harder to
  use than the thing it is explaining.
- **Names have to produce unique IDs.** Two pages both called "Rules" in different
  branches are fine; the builder quietly numbers the second one.
- **A button that points at a page you later deleted will block saving.** The
  error names the missing page.
- **A whole guide can be up to 256 KB.** That is a lot of text; you are unlikely
  to hit it unless you paste in something enormous.

## Blocks

These are the six things you can drag onto a page. A page holds up to **10** of
them.

### Text

Plain text with Discord formatting. Up to **4000 characters**.

Formatting that works: `**bold**`, `*italic*`, `__underline__`, `~~strikethrough~~`,
`# Heading`, `## Smaller heading`, `- bullet`, `> quote`, `` `code` ``, `-# small
grey text`, links, custom emoji, `<#channel>` and `<@role>` mentions.

### Separator

A thin dividing line. No settings, it just breaks things up.

### Section

Text with something attached on the right side.

- **1 to 3 text blocks** on the left.
- **One attachment** on the right, and it is required. Pick either:
  - **Thumbnail** - shows the viewer's own avatar. This is the only thing a
    thumbnail can show; it cannot display a picture from a URL. Use a Media
    Gallery for that.
  - **Button** - a normal button, same options as below.

### Action Row

A row of controls. It holds **either buttons or one dropdown**, never both.

- **Buttons:** 1 to 5 in a row.
- **Dropdown:** one per row.

### Container

A box with its own colored stripe that groups other blocks together. Useful for
visually separating a section of a page.

- Holds **1 to 10** blocks: text, separators, sections, action rows, and media
  galleries.
- **Containers cannot go inside containers.**
- Has its own accent color, which overrides the guide-wide one for that box.
- Can be marked as a spoiler, so the whole box is hidden until clicked.

### Media Gallery

A grid of images.

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

### What a guide button can do

| Action | What it does | What you pick |
|---|---|---|
| Go to page | Opens another page of your guide | The page, from a dropdown |
| Show channel | Points the member at a channel | The channel, from a dropdown |
| Show role | Shows information about a role | The role, from a dropdown |
| Link | Opens a website | The address, which must start with `https://` |

Link buttons are the odd one out: they open a URL and never trigger anything in
the bot, so they have no action. Every other button needs both an action and a
target.

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
| Action and target | Required - same three choices as buttons: go to page, show channel, show role |

## Colors

The accent color is the vertical stripe on the left of the message. Set it in the
top bar for the whole guide, or per container. Any hex color works, for example
`#5865F2`.

## What is not allowed

Every save is scanned for content that has no business in a Discord message:

- HTML and script markup, for example `<script>`, `<iframe>`, `<img onerror=...>`.
- `javascript:` links.
- Invisible and text-direction characters, which can be used to make a message
  read differently than it actually is.

Normal text, emoji, Discord mentions, and non-English scripts are all fine. If you
see a "disallowed markup" error, it is almost always text pasted in from a website.

## Navigation you get for free

You never build these - the bot adds them:

- **Back**, **Main Menu**, and **Search** buttons on every page.
- A **dropdown of child pages** on any page that has pages inside it.
- A **breadcrumb trail** showing where in the guide the member currently is.

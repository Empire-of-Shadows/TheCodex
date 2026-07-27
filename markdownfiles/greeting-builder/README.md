# Greeting Builder - Getting Started

This is the message your server posts when somebody new joins. You design it
here, the bot sends it to your greeting channel the moment a member walks in.

Unlike the guide, there are no pages. A greeting message is one screen: some text,
maybe the new member's avatar, and a few buttons that help them get started.

## Before it will send

Two things have to be true:

1. You have designed a message here and pressed **Save**.
2. A greeting channel is set for your server (Admin panel, New Members section).

If either is missing, joins happen quietly and no greeting is posted.

## A tour of the screen

**Top bar**
- **Guide / Greeting / Board** - switches between the three builders. Your work in
  the others is kept, so you can flip back and forth freely.
- **Accent** - the color of the stripe down the left edge of the message.
- **Import JSON / Export JSON** - save a backup to your computer, or load one back
  in. Handy for copying a design between servers.
- **Save** - writes the message to the bot. It stays greyed out until you have
  changes, and it will not let you save while there are errors.

**Left sidebar**
- **Components** - the blocks you can drag onto the message.

**Middle**
- The canvas, showing your message. Drag blocks here from the left, click a block
  to select it, drag blocks up and down to reorder.
- **Preview** - switches to a live mock-up of what the message will look like.
- **Docs** - this panel.
- The counter shows how many blocks you have used. The limit is 10.

**Right panel**
- Properties for whatever block you have selected: text, button labels, colors,
  what a button does.
- Below that, any problems with your message. Fix everything listed here and the
  Save button turns back on.

## Building your first greeting message

1. Drag a **Section** onto the canvas. A section is text with something attached
   on the right.
2. Select it and set the attachment to **Thumbnail**, which shows the new
   member's own avatar.
3. In the text, write something like:
   `# Welcome to {guild_name}, {member}!` on the first line and
   `You are member #{member_count}` on the second. Those words in braces fill
   themselves in per member - see the Placeholders page.
4. Drag an **Action Row** underneath and add a couple of buttons. Pick what each
   one does from the dropdown, for example "Opens the server guide menu".
5. Hit **Preview** to see it, then **Save**.

The next person to join gets the new message.

## Keyboard shortcuts

| Keys | What it does |
|---|---|
| `Ctrl` + `S` | Save |
| `Ctrl` + `D` | Duplicate the selected block |
| `Delete` | Remove the selected block |
| `Esc` | Deselect |

## Good habits

- **Keep it short.** New members skim. Three lines and two buttons beats a wall of
  text nobody reads.
- **Give them one obvious next step.** A single "Open the Guide" button does more
  than six competing ones.
- **Mind the ping.** `{member}` mentions the new member, which notifies them. Use
  it once, at the top, not in every line.
- **Preview before saving.** Placeholders show as sample values in preview, so you
  can see the real shape of the message.

## The other pages of these docs

- **Schema Reference** - every block, every field, and every limit.
- **Placeholders** - words like `{member_name}` that fill themselves in.
- **Examples** - ready-made layouts you can copy.

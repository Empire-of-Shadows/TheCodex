# Guide Builder - Getting Started

The guide is your server's built-in handbook. Members open it from a button or by
mentioning the bot, and they get a menu they can click through: rules, channel
explanations, FAQs, role info, whatever you want to put in it.

This builder is where you create that handbook. You drag blocks onto a page,
type your text, and press Save. No file editing, no code.

## The big idea: pages inside pages

A guide is a set of **pages**. A page can hold content, or it can hold other
pages, or both.

```
Main Menu
  Getting Started        (has its own text, plus two pages inside it)
    About Us
    Server Rules
  Channel Guide          (has two pages inside it)
    Chat Channels
    Gaming Channels
  FAQ                    (just content, nothing inside)
```

When a member opens a page that has pages inside it, the bot automatically adds a
dropdown so they can go deeper. It also adds Back, Main Menu, and Search buttons
to every page for you. You never have to build navigation yourself - just build
the pages.

## A tour of the screen

**Top bar**
- **Guide / Welcome** - switches between the two builders. Your work in the other
  one is kept, so you can flip back and forth freely.
- **Accent** - the color of the stripe down the left edge of your guide.
- **Import JSON / Export JSON** - save a backup to your computer, or load one back
  in. Handy for copying a guide between servers.
- **Save** - writes your guide to the bot. It stays greyed out until you have
  changes, and it will not let you save while there are errors.

**Left sidebar**
- **Components** - the blocks you can drag onto the page.
- **Pages** - your page tree. Add, rename, duplicate, delete, and drag pages
  around to reorder or nest them.

**Middle**
- The canvas, showing the page you have selected. Drag blocks here from the left,
  click a block to select it, drag blocks up and down to reorder.
- **Preview** - switches to a live mock-up of what members will see. Buttons and
  dropdowns actually work in preview, so you can walk your whole guide the way a
  member would.
- **Docs** - this panel.
- The counter shows how many blocks the current page has. The limit is 10.

**Right panel**
- Properties for whatever block you have selected: text, button labels, colors,
  where a button goes.
- Below that, any problems with your guide. Fix everything listed here and the
  Save button turns back on.

## Building your first guide

1. In the **Pages** list on the left, click add and name your first page, for
   example "Server Rules".
2. Drag a **Text** block onto the canvas.
3. Click it and type your rules in the right panel. Discord formatting works:
   `**bold**`, `*italic*`, `# Heading`, `- bullet`, and `-# small text`.
4. Add more pages the same way. Drag a page onto another page in the tree to nest
   it inside.
5. Hit **Preview** and click through it as a member would.
6. Hit **Save**.

Members see the change immediately the next time they open the guide.

## Keyboard shortcuts

| Keys | What it does |
|---|---|
| `Ctrl` + `S` | Save |
| `Ctrl` + `D` | Duplicate the selected block |
| `Delete` | Remove the selected block |
| `Esc` | Deselect |

## Good habits

- **Short pages beat long pages.** If a page needs a lot of scrolling, split it
  into child pages and let people pick what they need.
- **Preview before saving.** It is the fastest way to catch a button that points
  at the wrong place.
- **Export a backup** before a big rewrite. If you do not like the result, import
  the old file and save.
- **Write for someone who joined five minutes ago.** They do not know your
  in-jokes, channel names, or role hierarchy yet.

## The other pages of these docs

- **Schema Reference** - every block, every field, and every limit.
- **Placeholders** - words like `{member_name}` that fill themselves in.
- **Examples** - ready-made layouts you can copy.

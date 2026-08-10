# Board Builder - Getting Started

The info board is a **static message** that sits in one of your channels and holds
information. Unlike the greeting, it is not sent to anyone - you post it once and it
stays there.

What makes it different from a plain pinned embed: the buttons and dropdown on it
can reply **privately**. Someone clicks "Server Rules", and only they see the rules.
The channel stays clean, and one tidy message can hold a whole handbook.

## Before you start

1. You need Manage Server (or a staff role) on the server.
2. Nothing else - the board picks its channel when you post it.

## A tour of the screen

**Top bar**
- **Guide / Greeting / Board** - switches between the three builders. Your work in
  the others is kept, so you can flip back and forth freely.
- **Accent** - the colour of the stripe down the left edge of the message.
- **Import JSON / Export JSON** - save a backup to your computer, or load one back in.
- **Save** - saves your layout. It does **not** push it to Discord; see Publishing below.

**Left sidebar**
- The component palette, same as the other builders - drag blocks onto the canvas.
- The **Board** list. This is the part that is unique to boards:
  - **Board message** - the message everyone sees in the channel.
  - **Private responses** - the extra pages a button or dropdown option reveals.
    Click one to edit it; the canvas switches to that response.

**Canvas** - what your message will look like. Hit **Preview** to click through it:
buttons open their response below the board, exactly like Discord's "Only you can
see this" reply.

**Right panel** - properties for whatever block you have selected, and any errors.

## Building your first board

1. Start on **Board message** and drop a **Container** onto the canvas.
2. Put a **Text** block inside it with a heading, e.g.
   `# Welcome to {guild_name}` and a line about what the channel is for.
3. In the left sidebar, click **+ Response**, name it *Server Rules*. The canvas
   switches to the new response - write your rules there.
4. Click **Board message** to go back, add an **Action Row** with a button, and in
   the right panel set its action to **Send a private reply** and pick *Server Rules*.
5. Repeat for anything else worth its own page: roles, FAQ, getting started.
6. **Save**.

## Publishing

Saving stores the layout. Everything to do with putting it on Discord happens in the
admin panel: run `/admin panel` in your server and open
**Info Board -> Post / Update Board**.

- **Not posted yet?** Pick a channel from the dropdown on that screen and the board
  goes up there.
- **Already posted?** Press the **Post / Update** button. That **edits the message
  already in the channel** rather than posting a new one, so the board never
  duplicates. Do this each time you change the layout and save.
- **Want it in a different channel?** Pick the new channel from the same dropdown.
  The board is posted there and the old copy is removed, so you never end up with
  two.

**Info Board -> Board Status**, on the same panel, tells you where the board is
currently posted, how many blocks and private responses it has, and whether the
layout is valid.

## Things worth knowing

- If you delete the board message in Discord by hand, **Post / Update Board** puts a
  fresh one back in the same channel.
- A button pointing at a response you later delete will fail validation, and the
  builder tells you exactly which button is dangling. Fix it before saving.
- Responses can have their own buttons pointing at other responses, so you can build
  a small branching handbook.
- The board survives bot restarts. Nothing needs re-posting after a deploy.

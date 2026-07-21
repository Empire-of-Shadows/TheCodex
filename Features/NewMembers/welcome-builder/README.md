# Welcome Builder

The welcome builder lets you design a fully custom welcome message for new members using a JSON layout file. When a new member joins, the bot renders the JSON into a Discord Components v2 `LayoutView` and sends it to your configured welcome channel.

## How it works

1. **JSON file** - You write a `.json` file describing the layout: accent color, separators, text blocks, sections with accessories (thumbnails or buttons), action rows (buttons or select menus), containers, media galleries, and files.
2. **Admin panel upload** - You upload the file via **Admin Panel → New Members → Welcome Message Builder**.
3. **Schema validation** - The schema validator checks all fields, types, and constraints before saving. Non-link buttons and select options use named **actions** from the action registry (e.g. `"action": "open_guide"`) instead of raw `custom_id` strings.
4. **WelcomeRenderer** - On member join, `WelcomeRenderer.render()` reads the stored config, substitutes placeholders, encodes actions into Discord custom IDs, and builds a `discord.ui.LayoutView`.
5. **Action dispatcher** - When a user clicks a button or selects an option, `dispatch_welcome_action()` decodes the custom ID, looks up the handler in the action registry, and runs it.

## Getting the template

Run `/admin welcome-template` to receive the default layout as a ready-to-edit `welcome_template.json` file. Open it in any text editor, customize it, then upload.

## Uploading a layout

1. Open `/admin panel` → **New Members** → **Welcome Message Builder**
2. Click **Upload JSON**
3. Attach your `.json` file

The bot validates the schema before saving. If validation fails you will receive a specific error message.

## Resetting to no layout

In the same panel node, click **Clear** to remove the stored layout. When no layout is configured, welcome messages are skipped (a warning is logged).

## Reference docs

- [`schema.md`](schema.md) - Full JSON schema reference with all fields and constraints
- [`placeholders.md`](placeholders.md) - All supported `{placeholder}` tokens and where they apply
- [`examples.md`](examples.md) - Ready-to-use example layouts

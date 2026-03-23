# Guide Builder

The guide builder lets you create a fully custom server guide using a JSON page-tree file. When a member opens the guide, the bot renders the JSON into a Discord Components V2 `LayoutView` with automatic navigation chrome (breadcrumbs, Back, Main Menu, Search).

## How it works

1. **JSON file** — You write a `.json` file describing a page tree: top-level pages, nested children, and content for each page using Components V2 (text, sections, buttons, media galleries, containers, etc.).
2. **Admin panel upload** — You upload the file via **Admin Panel → Guide → Guide JSON Builder → Upload JSON**.
3. **Schema validation** — The validator checks all fields, types, page ID uniqueness, navigate targets, nesting depth, and component constraints before saving.
4. **GuideRenderer** — When a member opens the guide, `GuideRenderer` reads the stored page tree, substitutes placeholders, builds navigation chrome, and renders a `discord.ui.LayoutView`.
5. **Navigation** — The bot automatically adds breadcrumb trails, Back/Main Menu/Search buttons, and dropdown selects for child pages. Users navigate by clicking buttons or selecting from dropdowns.

## How the page tree works

The guide uses a **page-tree model** — pages contain other pages via the `children` array, creating a navigable hierarchy.

### Key concepts

- **A page with `children`** automatically gets a dropdown select so users can navigate into child pages.
- **A page with `content` only** is a leaf page — it displays its content with no dropdown.
- **A page with both `content` and `children`** displays its content AND shows a dropdown below it for navigating to children.
- **Children are just page objects** nested inside parent pages. They follow the exact same schema, recursively. A child can have its own children, creating deeper levels.
- **Navigation chrome is automatic** — the renderer adds Back, Main Menu, and Search buttons to every page. You never need to add these yourself.
- **Breadcrumb trails** show the user's path through the tree (e.g. `Getting Started > Server Rules`).

### Example structure

```
Main Menu (auto-generated)
├── Getting Started          ← has content + children
│   ├── About Us             ← leaf page (content only)
│   └── Server Rules         ← leaf page (content only)
├── Channels Guide           ← has content + children
│   ├── General Channels     ← leaf page
│   └── Gaming Channels      ← leaf page
└── FAQ                      ← leaf page (content only)
```

When a user opens "Getting Started", they see:
1. The page's content (text, images, etc.)
2. A dropdown with "About Us" and "Server Rules" options
3. Navigation buttons: Back, Main Menu, Search

### How this differs from the old system

The old guide system used embed types and select menus to manually define hierarchy. The new system uses explicit `children` arrays — you just nest pages inside pages and the navigation UI is built automatically.

## Getting the template

Run `/admin guide-template` to receive the default layout as a ready-to-edit `guide_template.json` file. Open it in any text editor, customize it, then upload.

## Uploading a layout

1. Open `/admin panel` → **Guide** → **Guide JSON Builder**
2. Click **Upload JSON**
3. Attach your `.json` file

The bot validates the schema before saving. If validation fails you will receive a specific error message telling you exactly what went wrong and where.

## Clearing / resetting

In the same panel, click **Clear** to revert to the default template. The default template provides a basic guide structure you can build on.

## Reference docs

- [`schema.md`](schema.md) — Full JSON schema reference with all fields and constraints
- [`placeholders.md`](placeholders.md) — All supported `{placeholder}` tokens and where they apply
- [`examples.md`](examples.md) — Ready-to-use example layouts (valid and invalid)

# Guide Builder - Examples

Layouts you can copy. Save any of these as a `.json` file and use **Import JSON**
in the top bar to load it, then edit it in the builder like anything else.

Importing replaces what is currently loaded, so export a backup first if you have
work you want to keep.

## 1. The simplest possible guide

One page, one block of text.

```json
{
  "accent_color": "#5865F2",
  "pages": [
    {
      "id": "welcome",
      "label": "Welcome",
      "icon": "👋",
      "content": {
        "components": [
          {
            "type": "text",
            "content": "# Welcome to {guild_name}\nGlad you are here, {member_name}. Use the buttons below to look around."
          }
        ]
      }
    }
  ]
}
```

## 2. A page with pages inside it

The bot adds the dropdown for the child pages by itself. You just nest them.

```json
{
  "accent_color": "#5865F2",
  "pages": [
    {
      "id": "getting-started",
      "label": "Getting Started",
      "description": "New here? Start with this.",
      "icon": "🚀",
      "content": {
        "components": [
          { "type": "text", "content": "# Getting Started\nPick a topic below." }
        ]
      },
      "children": [
        {
          "id": "about-us",
          "label": "About Us",
          "content": {
            "components": [
              { "type": "text", "content": "We are a gaming community built around playing together, not grinding alone." }
            ]
          }
        },
        {
          "id": "server-rules",
          "label": "Server Rules",
          "content": {
            "components": [
              { "type": "text", "content": "# Rules\n- Be decent to people\n- No spam or self promotion\n- Keep it safe for work\n- Listen to staff" }
            ]
          }
        }
      ]
    }
  ]
}
```

## 3. Text with a picture beside it, and a row of buttons

A section puts the reader's avatar on the right. The action row underneath mixes
a jump to another page, a channel pointer, and an outside link.

```json
{
  "accent_color": "#2ECC71",
  "pages": [
    {
      "id": "home",
      "label": "Home",
      "content": {
        "components": [
          {
            "type": "section",
            "content": [
              { "type": "text", "content": "# {guild_name}\nHey {member_name}, here is the short version of how this place works." }
            ],
            "accessory": { "type": "thumbnail", "media": "member_avatar" }
          },
          { "type": "separator" },
          {
            "type": "action_row",
            "buttons": [
              { "type": "button", "style": "primary", "label": "Read the rules", "action": "navigate", "target": "server-rules" },
              { "type": "button", "style": "secondary", "label": "Say hi", "action": "channel", "target": "123456789012345678" },
              { "type": "button", "style": "link", "label": "Our website", "url": "https://eosofficial.club" }
            ]
          }
        ]
      }
    },
    {
      "id": "server-rules",
      "label": "Server Rules",
      "content": {
        "components": [
          { "type": "text", "content": "# Rules\n- Be decent to people\n- No spam\n- Listen to staff" }
        ]
      }
    }
  ]
}
```

The long number in the channel button is a Discord channel ID. You never have to
find it yourself - in the builder you pick the channel from a dropdown and it
fills that in.

## 4. A dropdown menu of topics

When you want one tidy menu instead of a wall of buttons.

```json
{
  "pages": [
    {
      "id": "help-desk",
      "label": "Help Desk",
      "content": {
        "components": [
          { "type": "text", "content": "# Help Desk\nWhat do you need a hand with?" },
          {
            "type": "action_row",
            "select": {
              "placeholder": "Choose a topic...",
              "options": [
                { "label": "How do I get roles?", "description": "Self-assign roles and what they unlock", "emoji": "🎭", "action": "navigate", "target": "roles" },
                { "label": "Where do I report a problem?", "emoji": "🛟", "action": "channel", "target": "123456789012345678" },
                { "label": "What does Member get me?", "emoji": "⭐", "action": "role", "target": "987654321098765432" }
              ]
            }
          }
        ]
      }
    },
    {
      "id": "roles",
      "label": "Roles",
      "content": {
        "components": [
          { "type": "text", "content": "Grab your roles in the roles channel. They control which channels you can see." }
        ]
      }
    }
  ]
}
```

## 5. A boxed section with images

A container groups blocks into a box with its own colored stripe. Handy for
setting one part of a page apart from the rest.

```json
{
  "pages": [
    {
      "id": "events",
      "label": "Events",
      "content": {
        "components": [
          {
            "type": "container",
            "accent_color": "#E67E22",
            "components": [
              { "type": "text", "content": "## Game Night\nEvery Friday, 8pm. No signup, just turn up." },
              {
                "type": "media_gallery",
                "items": [
                  { "media": "https://example.com/game-night.png", "description": "Game night banner" }
                ]
              },
              { "type": "separator" },
              {
                "type": "action_row",
                "buttons": [
                  { "type": "button", "style": "success", "label": "Events channel", "action": "channel", "target": "123456789012345678" }
                ]
              }
            ]
          }
        ]
      }
    }
  ]
}
```

Image addresses have to be direct links to an image file and start with
`https://`. A link to a page that happens to show an image will not load.

## 6. A small but complete guide

Three top-level topics, one with children, and a home page that routes into them.

```json
{
  "accent_color": "#5865F2",
  "pages": [
    {
      "id": "start-here",
      "label": "Start Here",
      "description": "The five minute version",
      "icon": "🧭",
      "content": {
        "components": [
          {
            "type": "section",
            "content": [
              { "type": "text", "content": "# Welcome, {member_name}\nThere are {member_count} of us. Here is where to begin." }
            ],
            "accessory": { "type": "thumbnail", "media": "member_avatar" }
          },
          {
            "type": "action_row",
            "buttons": [
              { "type": "button", "style": "primary", "label": "Rules", "action": "navigate", "target": "rules" },
              { "type": "button", "style": "secondary", "label": "Channels", "action": "navigate", "target": "channels" },
              { "type": "button", "style": "secondary", "label": "FAQ", "action": "navigate", "target": "faq" }
            ]
          }
        ]
      }
    },
    {
      "id": "rules",
      "label": "Rules",
      "icon": "📜",
      "content": {
        "components": [
          { "type": "text", "content": "# Rules\n- Be decent to people\n- No spam or self promotion\n- Keep it safe for work\n- Staff decisions are final" }
        ]
      }
    },
    {
      "id": "channels",
      "label": "Channels",
      "icon": "💬",
      "content": {
        "components": [
          { "type": "text", "content": "# Channels\nPick a category below to see what is in it." }
        ]
      },
      "children": [
        {
          "id": "chat-channels",
          "label": "Chat",
          "content": {
            "components": [
              { "type": "text", "content": "General chat, memes, and off topic. Keep it friendly." }
            ]
          }
        },
        {
          "id": "gaming-channels",
          "label": "Gaming",
          "content": {
            "components": [
              { "type": "text", "content": "Looking for a group, game specific chat, and clips." }
            ]
          }
        }
      ]
    },
    {
      "id": "faq",
      "label": "FAQ",
      "icon": "❓",
      "content": {
        "components": [
          { "type": "text", "content": "# FAQ\n**How do I get roles?**\nCheck the roles channel.\n\n**Can I invite friends?**\nYes, always.\n\n**How do I report someone?**\nMessage any staff member." }
        ]
      }
    }
  ]
}
```

## Mistakes that block saving

**"must have content, children, or both"**
An empty page. Either put something on it or delete it.

**"targets page ... which does not exist"**
A button or dropdown option points at a page you renamed or deleted. Reselect the
destination in the right panel.

**"cannot have both buttons and select"**
One action row is trying to hold both. Split them into two rows.

**"accessory is required"**
A section with no attachment. Every section needs either a thumbnail or a button
on its right side.

**"components has 12 items; max is 10"**
Too many blocks on one page. Move some onto a child page - it usually reads better
anyway.

**"url is required for link buttons and must start with https://"**
A link button with no address, or one starting with `http://`.

**"page nesting exceeds maximum depth of 5"**
Pages inside pages inside pages, five levels down. Flatten a branch.

**"contains disallowed HTML or script markup"**
Text pasted from a website brought hidden markup with it. Retype the line, or
paste it into a plain text editor first and copy it back out.

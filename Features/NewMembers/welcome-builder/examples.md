# Welcome Builder - Example Layouts

---

## Minimal

A simple separator, a text greeting, and a single action row.

```json
{
  "accent_color": "#5865F2",
  "components": [
    {"type": "separator"},
    {"type": "text", "content": "# Welcome to {guild_name}, {member}!\nYou are member #{member_count}."},
    {
      "type": "action_row",
      "buttons": [
        {"type": "button", "style": "success", "label": "Guide", "action": "open_guide"}
      ]
    }
  ]
}
```

---

## Standard (matches `/admin welcome-template`)

The default template returned by `/admin welcome-template`. Replace the placeholder channel URLs.

```json
{
  "accent_color": "#5865F2",
  "components": [
    {"type": "separator"},
    {
      "type": "section",
      "content": [
        {"type": "text", "content": "# Welcome to {guild_name}, {member}!\n*You are member #{member_count}!*"}
      ],
      "accessory": {"type": "thumbnail", "media": "member_avatar"}
    },
    {
      "type": "action_row",
      "buttons": [
        {"type": "button", "style": "success", "label": "Guide", "action": "open_guide"},
        {"type": "button", "style": "link", "label": "Rules", "url": "https://discord.com/channels/GUILD/CHANNEL"},
        {"type": "button", "style": "link", "label": "Come Chat!", "url": "https://discord.com/channels/GUILD/CHANNEL"}
      ]
    },
    {"type": "separator"},
    {
      "type": "section",
      "content": [
        {"type": "text", "content": "**Explore and have fun!**\n- Play games, compete in leaderboards\n- Join voice ({voice_active} active now!)"}
      ],
      "accessory": {
        "type": "button", "style": "link", "label": "Server Info",
        "url": "https://discord.com/channels/GUILD/CHANNEL"
      }
    },
    {"type": "separator"},
    {
      "type": "section",
      "content": [{"type": "text", "content": "Some other channels you might like"}],
      "accessory": {"type": "button", "style": "secondary", "label": "All Channels", "action": "channel_list"}
    },
    {
      "type": "action_row",
      "buttons": [
        {"type": "button", "style": "link", "label": "Media", "url": "https://discord.com/channels/GUILD/CHANNEL"},
        {"type": "button", "style": "link", "label": "Game Clips", "url": "https://discord.com/channels/GUILD/CHANNEL"},
        {"type": "button", "style": "link", "label": "Gamer Chat", "url": "https://discord.com/channels/GUILD/CHANNEL"}
      ]
    },
    {"type": "separator"},
    {"type": "text", "content": "-# {random_greeting}"}
  ]
}
```

---

## Random greeting

Uses `{random_greeting}` to give every new member a unique, themed welcome pulled from 100+ messages.

```json
{
  "accent_color": "#5865F2",
  "components": [
    {"type": "separator"},
    {
      "type": "section",
      "content": [
        {"type": "text", "content": "{random_greeting}"}
      ],
      "accessory": {"type": "thumbnail", "media": "member_avatar"}
    },
    {"type": "text", "content": "Check out the guide and explore our channels!"},
    {
      "type": "action_row",
      "buttons": [
        {"type": "button", "style": "success", "label": "Guide", "action": "open_guide"},
        {"type": "button", "style": "link", "label": "Rules", "url": "https://discord.com/channels/GUILD/CHANNEL"}
      ]
    }
  ]
}
```

---

## Thumbnail-focused

Leads with the member's avatar prominently in a section, followed by a short welcome text and a single button row.

```json
{
  "accent_color": "#57F287",
  "components": [
    {"type": "separator"},
    {
      "type": "section",
      "content": [
        {"type": "text", "content": "## Hey {member_name}!"},
        {"type": "text", "content": "Welcome to **{guild_name}**. You're member #{member_count}."}
      ],
      "accessory": {
        "type": "thumbnail",
        "media": "member_avatar",
        "description": "New member avatar"
      }
    },
    {"type": "separator"},
    {"type": "text", "content": "Read the rules and say hello in chat. {voice_active} voice channels are active right now!"},
    {
      "type": "action_row",
      "buttons": [
        {"type": "button", "style": "success", "label": "Guide", "action": "open_guide"},
        {"type": "button", "style": "link", "label": "Rules", "url": "https://discord.com/channels/GUILD/CHANNEL"}
      ]
    }
  ]
}
```

---

## Media gallery

Showcase server screenshots or artwork alongside the welcome message.

```json
{
  "accent_color": "#ED4245",
  "components": [
    {"type": "text", "content": "# Welcome to {guild_name}, {member}!"},
    {
      "type": "media_gallery",
      "items": [
        {"media": "https://example.com/server-banner.png", "description": "Our server banner"},
        {"media": "https://example.com/community-event.png", "description": "Recent community event"}
      ]
    },
    {
      "type": "action_row",
      "buttons": [
        {"type": "button", "style": "success", "label": "Guide", "action": "open_guide"},
        {"type": "button", "style": "primary", "label": "Server Info", "action": "server_info"}
      ]
    }
  ]
}
```

---

## Container with accent color

Group related content inside a styled container.

```json
{
  "components": [
    {"type": "text", "content": "# Welcome, {member}!"},
    {
      "type": "container",
      "accent_color": "#5865F2",
      "components": [
        {"type": "text", "content": "**Getting Started**"},
        {"type": "separator"},
        {"type": "text", "content": "Check out the guide and explore our channels."},
        {
          "type": "action_row",
          "buttons": [
            {"type": "button", "style": "success", "label": "Guide", "action": "open_guide"},
            {"type": "button", "style": "secondary", "label": "All Channels", "action": "channel_list"}
          ]
        }
      ]
    }
  ]
}
```

---

## Select dropdown

Use a select menu to let new members pick what info they want to see.

```json
{
  "accent_color": "#FEE75C",
  "components": [
    {
      "type": "section",
      "content": [{"type": "text", "content": "# Welcome to {guild_name}, {member}!"}],
      "accessory": {"type": "thumbnail", "media": "member_avatar"}
    },
    {
      "type": "action_row",
      "select": {
        "placeholder": "What would you like to know?",
        "options": [
          {"label": "Server Guide", "action": "open_guide", "description": "Browse the full guide", "emoji": "📖"},
          {"label": "Server Info", "action": "server_info", "description": "Stats and boost info", "emoji": "📊"},
          {"label": "All Channels", "action": "channel_list", "description": "Browse channel categories", "emoji": "📋"},
          {"label": "Getting Started", "action": "getting_started", "description": "Tips for new members", "emoji": "🚀"}
        ]
      }
    }
  ]
}
```

---

## Action hub

Showcases every available action across buttons and a select menu. Uses button `emoji`, the `danger` style, and all actions not covered by other examples (`suggest`, `browse_drops`, `server_rules`, `role_info`).

```json
{
  "accent_color": "#EB459E",
  "components": [
    {
      "type": "section",
      "content": [
        {"type": "text", "content": "# Welcome, {member}!"},
        {"type": "text", "content": "Here's everything you can explore in **{guild_name}**."},
        {"type": "text", "content": "-# Member #{member_count}"}
      ],
      "accessory": {"type": "thumbnail", "media": "member_avatar"}
    },
    {"type": "separator"},
    {
      "type": "action_row",
      "buttons": [
        {"type": "button", "style": "success", "label": "Guide", "emoji": "📖", "action": "open_guide"},
        {"type": "button", "style": "primary", "label": "Suggest", "emoji": "💡", "action": "suggest"},
        {"type": "button", "style": "secondary", "label": "Free Drops", "emoji": "🎁", "action": "browse_drops"},
        {"type": "button", "style": "danger", "label": "Rules", "emoji": "📜", "action": "server_rules"}
      ]
    },
    {
      "type": "action_row",
      "select": {
        "placeholder": "More things to explore…",
        "options": [
          {"label": "Server Info", "action": "server_info", "description": "Stats and boost status", "emoji": "📊"},
          {"label": "All Channels", "action": "channel_list", "description": "Browse every channel", "emoji": "📋"},
          {"label": "Getting Started", "action": "getting_started", "description": "Tips for new members", "emoji": "🚀"},
          {"label": "Role Info", "action": "role_info", "description": "See all server roles", "emoji": "🏷️"}
        ]
      }
    }
  ]
}
```

---

## Spoiler reveal

Uses a `container` with `spoiler: true` to hide content behind a click, a `media_gallery` with spoiler items, and a `file` component. Shows off optional fields that add interactivity.

```json
{
  "accent_color": "#5865F2",
  "components": [
    {"type": "text", "content": "# {member} just joined {guild_name}!"},
    {
      "type": "container",
      "accent_color": "#57F287",
      "spoiler": true,
      "components": [
        {"type": "text", "content": "🎉 **Surprise!** Click to see what's waiting for you."},
        {"type": "separator"},
        {"type": "text", "content": "{random_greeting}"},
        {
          "type": "action_row",
          "buttons": [
            {"type": "button", "style": "success", "label": "Open Guide", "emoji": "📖", "action": "open_guide"},
            {"type": "button", "style": "link", "label": "Say Hi!", "url": "https://discord.com/channels/GUILD/CHANNEL"}
          ]
        }
      ]
    },
    {
      "type": "media_gallery",
      "items": [
        {"media": "https://example.com/server-banner.png", "description": "Our server banner"},
        {"media": "https://example.com/secret-art.png", "description": "Hidden community art", "spoiler": true}
      ]
    },
    {"type": "file", "media": "https://example.com/welcome-guide.png"}
  ]
}
```

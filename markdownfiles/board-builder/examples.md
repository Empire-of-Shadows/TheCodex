# Board Builder - Examples

Paste any of these into **Import JSON** to try them, then edit to taste.

## 1. The simplest board

One message, one button, one private reply behind it.

```json
{
  "accent_color": "#4D0EB3",
  "components": [
    { "type": "text", "content": "# Welcome to {guild_name}\nTap below for the rules." },
    {
      "type": "action_row",
      "buttons": [
        { "type": "button", "style": "primary", "label": "Server Rules", "action": "reply", "target": "rules" }
      ]
    }
  ],
  "responses": [
    {
      "id": "rules",
      "label": "Server Rules",
      "components": [
        { "type": "text", "content": "## Rules\n1. Be respectful.\n2. Keep it appropriate.\n3. No spam." }
      ]
    }
  ]
}
```

## 2. A boxed board with a row of topics

The container gives it a coloured edge and holds everything together.

```json
{
  "accent_color": "#4D0EB3",
  "components": [
    {
      "type": "container",
      "components": [
        { "type": "text", "content": "# Welcome to {guild_name}" },
        { "type": "separator" },
        { "type": "text", "content": "Everything you need is behind these buttons. Only you see what you open." },
        {
          "type": "action_row",
          "buttons": [
            { "type": "button", "style": "primary",   "label": "Rules",    "action": "reply", "target": "rules" },
            { "type": "button", "style": "secondary", "label": "Roles",    "action": "reply", "target": "roles" },
            { "type": "button", "style": "secondary", "label": "FAQ",      "action": "reply", "target": "faq" },
            { "type": "button", "style": "link",      "label": "Website",  "url": "https://eosofficial.club" }
          ]
        }
      ]
    }
  ],
  "responses": [
    { "id": "rules", "label": "Rules",  "components": [{ "type": "text", "content": "## Rules\nBe decent to each other." }] },
    { "id": "roles", "label": "Roles",  "components": [{ "type": "text", "content": "## Roles\nSome are automatic, some you pick." }] },
    { "id": "faq",   "label": "FAQ",    "components": [{ "type": "text", "content": "## FAQ\n**How do I get help?**\nMention me." }] }
  ]
}
```

## 3. A dropdown instead of buttons

Better when you have more than five topics. Up to 25 options fit here.

```json
{
  "components": [
    { "type": "text", "content": "# {guild_name} Information Desk\nPick a topic from the menu." },
    {
      "type": "action_row",
      "select": {
        "placeholder": "What are you looking for?",
        "options": [
          { "label": "Server rules",     "description": "The short version",        "action": "reply",   "target": "rules" },
          { "label": "How roles work",   "description": "Earning and picking roles", "action": "reply",  "target": "roles" },
          { "label": "Getting started",  "description": "Your first ten minutes",   "action": "reply",   "target": "start" },
          { "label": "Head to general",  "description": "Come say hello",           "action": "channel", "target": "234567890123456789" }
        ]
      }
    }
  ],
  "responses": [
    { "id": "rules", "components": [{ "type": "text", "content": "## Rules\n..." }] },
    { "id": "roles", "components": [{ "type": "text", "content": "## Roles\n..." }] },
    { "id": "start", "components": [{ "type": "text", "content": "## Getting Started\n..." }] }
  ]
}
```

## 4. Responses that lead to other responses

A response is a full layout, so it can carry its own buttons. This is how you build a
small branching handbook without cluttering the channel.

```json
{
  "components": [
    { "type": "text", "content": "# {guild_name} Handbook" },
    {
      "type": "action_row",
      "buttons": [
        { "type": "button", "style": "primary", "label": "Open the handbook", "action": "reply", "target": "index" }
      ]
    }
  ],
  "responses": [
    {
      "id": "index",
      "label": "Handbook index",
      "components": [
        { "type": "text", "content": "## Handbook\nHi {member_name} - where would you like to start?" },
        {
          "type": "action_row",
          "buttons": [
            { "type": "button", "style": "secondary", "label": "Rules",   "action": "reply", "target": "rules" },
            { "type": "button", "style": "secondary", "label": "Roles",   "action": "reply", "target": "roles" }
          ]
        }
      ]
    },
    {
      "id": "rules",
      "components": [
        { "type": "text", "content": "## Rules\nBe decent." },
        { "type": "action_row", "buttons": [
          { "type": "button", "style": "secondary", "label": "Back to the handbook", "action": "reply", "target": "index" }
        ]}
      ]
    },
    {
      "id": "roles",
      "components": [
        { "type": "text", "content": "## Roles\nPick what suits you." },
        { "type": "action_row", "buttons": [
          { "type": "button", "style": "secondary", "label": "Back to the handbook", "action": "reply", "target": "index" }
        ]}
      ]
    }
  ]
}
```

## 5. Self-assignable roles

Each button toggles: clicking again takes the role away.

```json
{
  "components": [
    {
      "type": "container",
      "components": [
        { "type": "text", "content": "# Pick your roles\nTap to add, tap again to remove." },
        {
          "type": "action_row",
          "buttons": [
            { "type": "button", "style": "secondary", "label": "Gamer",       "action": "role", "target": "111111111111111111" },
            { "type": "button", "style": "secondary", "label": "Movie Night", "action": "role", "target": "222222222222222222" },
            { "type": "button", "style": "secondary", "label": "Announcements", "action": "role", "target": "333333333333333333" }
          ]
        }
      ]
    }
  ]
}
```

Replace those IDs with your own - the builder's role dropdown fills them in for you.

## What not to do

- **Everything on the board message.** The whole point is that the board stays short
  and the detail hides behind buttons. If your board is a wall of text, move most of
  it into responses.
- **A response per sentence.** Group related things; 25 is the ceiling but five to
  eight reads better.
- **Live numbers.** The board is edited rarely, so any count you bake in goes stale.

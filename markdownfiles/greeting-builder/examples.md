# Greeting Builder - Examples

Layouts you can copy. Save any of these as a `.json` file and use **Import JSON**
in the top bar to load it, then edit it in the builder like anything else.

Importing replaces what is currently loaded, so export a backup first if you have
work you want to keep.

## 1. The simplest greeting

One line of text. Does the job.

```json
{
  "accent_color": "#5865F2",
  "components": [
    {
      "type": "text",
      "content": "# Welcome to {guild_name}, {member}!\nYou are member #{member_count}. Make yourself at home."
    }
  ]
}
```

## 2. Greeting with their avatar

A section puts the new member's avatar to the right of your text. This is the one
most servers want.

```json
{
  "accent_color": "#5865F2",
  "components": [
    {
      "type": "section",
      "content": [
        { "type": "text", "content": "# Welcome, {member}!" },
        { "type": "text", "content": "-# Member #{member_count} of {guild_name}" }
      ],
      "accessory": { "type": "thumbnail", "media": "member_avatar" }
    }
  ]
}
```

## 3. Greeting plus a row of helpful buttons

Everything these buttons show is private to the person who clicks, so your greeting
channel stays clean.

```json
{
  "accent_color": "#2ECC71",
  "components": [
    {
      "type": "section",
      "content": [
        { "type": "text", "content": "# Welcome to {guild_name}, {member}!" },
        { "type": "text", "content": "You are member #{member_count}. Start with the guide." }
      ],
      "accessory": { "type": "thumbnail", "media": "member_avatar" }
    },
    { "type": "separator" },
    {
      "type": "action_row",
      "buttons": [
        { "type": "button", "style": "primary", "label": "Open the Guide", "emoji": "📖", "action": "open_guide" },
        { "type": "button", "style": "secondary", "label": "Server Rules", "emoji": "📜", "action": "server_rules" },
        { "type": "button", "style": "secondary", "label": "Channels", "emoji": "💬", "action": "channel_list" }
      ]
    }
  ]
}
```

## 4. One dropdown instead of six buttons

When you want to offer a lot without cluttering the message.

```json
{
  "accent_color": "#9B59B6",
  "components": [
    {
      "type": "text",
      "content": "# Welcome, {member}!\nPick whatever you need from the menu below."
    },
    {
      "type": "action_row",
      "select": {
        "placeholder": "What would you like to see?",
        "options": [
          { "label": "The server guide", "description": "Rules, channels, and how things work", "emoji": "📖", "action": "open_guide" },
          { "label": "Server stats", "description": "Member count, boosts, and more", "emoji": "📊", "action": "server_info" },
          { "label": "Channel overview", "description": "What each part of the server is for", "emoji": "💬", "action": "channel_list" },
          { "label": "Roles", "description": "What the roles here mean", "emoji": "🎭", "action": "role_info" },
          { "label": "Free game drops", "description": "Current Prime Gaming and free offers", "emoji": "🎁", "action": "browse_drops" },
          { "label": "Send a suggestion", "description": "Tell us what the server is missing", "emoji": "💡", "action": "suggest" }
        ]
      }
    }
  ]
}
```

## 5. A boxed greeting with a random opener

A container gives the message its own framed look. `{random_greeting}` means the
greeting channel does not read identically every single time.

```json
{
  "accent_color": "#E67E22",
  "components": [
    {
      "type": "container",
      "accent_color": "#E67E22",
      "components": [
        {
          "type": "section",
          "content": [
            { "type": "text", "content": "# A new face appears" },
            { "type": "text", "content": "{random_greeting}" }
          ],
          "accessory": { "type": "thumbnail", "media": "member_avatar" }
        },
        { "type": "separator" },
        { "type": "text", "content": "-# {member_name} is member #{member_count}. {voice_active} voice channels are busy right now." },
        {
          "type": "action_row",
          "buttons": [
            { "type": "button", "style": "primary", "label": "Open the Guide", "action": "open_guide" },
            { "type": "button", "style": "link", "label": "Our website", "url": "https://eosofficial.club" }
          ]
        }
      ]
    }
  ]
}
```

## 6. The full treatment

Banner image, greeting, a short orientation, buttons, and a dropdown. This is
about as much as anyone should put in a greeting message.

```json
{
  "accent_color": "#5865F2",
  "components": [
    {
      "type": "media_gallery",
      "items": [
        { "media": "https://example.com/welcome-banner.png", "description": "Server banner" }
      ]
    },
    {
      "type": "section",
      "content": [
        { "type": "text", "content": "# Welcome to {guild_name}, {member}!" },
        { "type": "text", "content": "-# You are our {member_count}th member" }
      ],
      "accessory": { "type": "thumbnail", "media": "member_avatar" }
    },
    { "type": "separator" },
    {
      "type": "text",
      "content": "**Three things worth doing first**\n- Read the rules so you know the deal\n- Grab your roles to unlock the channels you care about\n- Say hello, we do not bite"
    },
    {
      "type": "action_row",
      "buttons": [
        { "type": "button", "style": "primary", "label": "Open the Guide", "emoji": "📖", "action": "open_guide" },
        { "type": "button", "style": "secondary", "label": "Rules", "emoji": "📜", "action": "server_rules" },
        { "type": "button", "style": "secondary", "label": "Getting Started", "emoji": "🚀", "action": "getting_started" }
      ]
    },
    {
      "type": "action_row",
      "select": {
        "placeholder": "Or browse something else...",
        "options": [
          { "label": "Server stats", "emoji": "📊", "action": "server_info" },
          { "label": "Channel overview", "emoji": "💬", "action": "channel_list" },
          { "label": "Roles", "emoji": "🎭", "action": "role_info" },
          { "label": "Free game drops", "emoji": "🎁", "action": "browse_drops" },
          { "label": "Send a suggestion", "emoji": "💡", "action": "suggest" }
        ]
      }
    }
  ]
}
```

## Mistakes that block saving

**"cannot have both buttons and select"**
One action row is trying to hold both. Split them into two rows.

**"accessory is required"**
A section with no attachment. Every section needs either a thumbnail or a button
on its right side.

**"media must be member_avatar"**
A thumbnail pointed at an image address. Thumbnails only ever show the new
member's avatar. For your own artwork, use a Media Gallery instead.

**"buttons has 6 items; max is 5"**
Too many buttons in one row. Add a second row, or move some into a dropdown.

**"components has 12 items; max is 10"**
Too many blocks overall. A greeting message is a doorway, not the whole house.

**"url is required for link buttons and must start with https://"**
A link button with no address, or one starting with `http://`.

**"is not a valid action"**
An imported file is using an action name this bot does not have. Open the button
in the right panel and pick from the dropdown.

**"contains disallowed HTML or script markup"**
Text pasted from a website brought hidden markup with it. Retype the line, or
paste it into a plain text editor first and copy it back out.

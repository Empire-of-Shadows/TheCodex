# Guide Builder - Example Layouts

## Valid examples

These examples pass schema validation and are ready to use.

---

### 1. Minimal - single page, one text component

The simplest possible guide: one page with one text block.

```json
{
  "pages": [
    {
      "label": "Welcome",
      "content": {
        "components": [
          {"type": "text", "content": "# Welcome to our server!\n\nThis is the server guide."}
        ]
      }
    }
  ]
}
```

---

### 2. Navigation buttons - cross-page navigate buttons

Pages that link to each other using navigate buttons.

```json
{
  "accent_color": "#5865F2",
  "pages": [
    {
      "id": "home",
      "label": "Home",
      "description": "Main guide page",
      "icon": "🏠",
      "content": {
        "components": [
          {"type": "text", "content": "# Server Guide\n\nWelcome! Choose a topic below."},
          {
            "type": "action_row",
            "buttons": [
              {"style": "primary", "label": "Rules", "action": "navigate", "target": "rules"},
              {"style": "success", "label": "Channels", "action": "navigate", "target": "channels"},
              {"style": "link", "label": "Website", "url": "https://example.com"}
            ]
          }
        ]
      }
    },
    {
      "id": "rules",
      "label": "Rules",
      "description": "Server rules and guidelines",
      "icon": "📜",
      "content": {
        "components": [
          {"type": "text", "content": "# Rules\n\n1. Be respectful\n2. No spam\n3. Have fun!"},
          {
            "type": "action_row",
            "buttons": [
              {"style": "secondary", "label": "Back to Home", "action": "navigate", "target": "home"}
            ]
          }
        ]
      }
    },
    {
      "id": "channels",
      "label": "Channels",
      "description": "Channel overview",
      "icon": "📺",
      "content": {
        "components": [
          {"type": "text", "content": "# Channels\n\nHere are our main channels:\n- General\n- Gaming\n- Media"}
        ]
      }
    }
  ]
}
```

---

### 3. Nested hierarchy - parent categories with children dropdown

A hierarchical guide. Parent pages get automatic dropdown navigation for their children.

```json
{
  "accent_color": "#4D0EB3",
  "pages": [
    {
      "id": "getting-started",
      "label": "Getting Started",
      "description": "New member guide",
      "icon": "👋",
      "order": 1,
      "content": {
        "components": [
          {"type": "text", "content": "# Getting Started\n\nSelect a subtopic below to learn more."}
        ]
      },
      "children": [
        {
          "id": "about",
          "label": "About Us",
          "description": "Who we are",
          "content": {
            "components": [
              {"type": "text", "content": "# About Us\n\nWe're a gaming community!"},
              {"type": "separator"},
              {
                "type": "section",
                "content": [{"type": "text", "content": "Check out our website for more info."}],
                "accessory": {"type": "button", "style": "link", "label": "Website", "url": "https://example.com"}
              }
            ]
          }
        },
        {
          "id": "rules",
          "label": "Server Rules",
          "description": "Community guidelines",
          "icon": "📜",
          "content": {
            "components": [
              {"type": "text", "content": "# Rules\n\nPlease be respectful and follow Discord TOS."}
            ]
          }
        }
      ]
    },
    {
      "id": "faq",
      "label": "FAQ",
      "description": "Frequently asked questions",
      "icon": "❓",
      "order": 2,
      "content": {
        "components": [
          {"type": "text", "content": "# FAQ\n\n**Q: How do I get roles?**\nCheck the role selection channel."}
        ]
      }
    }
  ]
}
```

---

### 4. Rich media - media gallery and thumbnails

Using media galleries and section thumbnails.

```json
{
  "accent_color": "#FF6B6B",
  "pages": [
    {
      "id": "showcase",
      "label": "Server Showcase",
      "description": "See what our server looks like",
      "icon": "🖼",
      "content": {
        "components": [
          {"type": "text", "content": "# Server Showcase\n\nHighlights from our community:"},
          {
            "type": "media_gallery",
            "items": [
              {"media": "https://example.com/banner.png", "description": "Our server banner"},
              {"media": "https://example.com/event.png", "description": "Community event", "spoiler": true}
            ]
          },
          {"type": "separator"},
          {
            "type": "section",
            "content": [
              {"type": "text", "content": "**Meet the team!**"},
              {"type": "text", "content": "Our moderators keep things running smoothly."}
            ],
            "accessory": {"type": "thumbnail", "media": "member_avatar", "description": "Your avatar"}
          }
        ]
      }
    }
  ]
}
```

---

### 5. Placeholder showcase - uses all 6 placeholders

Demonstrates every available placeholder.

```json
{
  "pages": [
    {
      "label": "Personalized Guide",
      "content": {
        "components": [
          {"type": "text", "content": "# Hello, {member}!\n\nWelcome to **{guild_name}**. You are one of {member_count} members!"},
          {"type": "separator"},
          {
            "type": "section",
            "content": [
              {"type": "text", "content": "There are currently **{voice_active}** active voice channels. Jump in and say hi, {member_name}!"}
            ],
            "accessory": {"type": "thumbnail", "media": "member_avatar"}
          },
          {"type": "separator"},
          {"type": "text", "content": "-# {random_greeting}"}
        ]
      }
    }
  ]
}
```

---

### 6. Deep nesting - 3 levels of children

Three levels of hierarchy: category → subcategory → detail page.

```json
{
  "accent_color": "#57F287",
  "pages": [
    {
      "id": "community",
      "label": "Community",
      "icon": "🌍",
      "children": [
        {
          "id": "events",
          "label": "Events",
          "description": "Community events",
          "icon": "🎉",
          "content": {
            "components": [
              {"type": "text", "content": "# Events\n\nBrowse our event categories below."}
            ]
          },
          "children": [
            {
              "id": "weekly-events",
              "label": "Weekly Events",
              "description": "Events that happen every week",
              "content": {
                "components": [
                  {"type": "text", "content": "# Weekly Events\n\n- **Movie Night** - Every Friday at 8 PM\n- **Game Tournament** - Every Saturday at 3 PM\n- **Trivia Night** - Every Wednesday at 7 PM"}
                ]
              }
            },
            {
              "id": "special-events",
              "label": "Special Events",
              "description": "One-time and seasonal events",
              "content": {
                "components": [
                  {"type": "text", "content": "# Special Events\n\nCheck announcements for upcoming special events!"}
                ]
              }
            }
          ]
        },
        {
          "id": "partnerships",
          "label": "Partnerships",
          "description": "Partner servers",
          "content": {
            "components": [
              {"type": "text", "content": "# Partnerships\n\nWe partner with other communities to bring you more content."}
            ]
          }
        }
      ]
    }
  ]
}
```

---

### 7. Mixed content + children - parent page with both

A parent page that has its own content displayed alongside the children dropdown.

```json
{
  "accent_color": "#FEE75C",
  "pages": [
    {
      "id": "roles",
      "label": "Roles & Perks",
      "description": "Server roles and what they unlock",
      "icon": "🏷️",
      "content": {
        "components": [
          {"type": "text", "content": "# Roles & Perks\n\nOur server uses a tiered role system. As you participate, you unlock new perks!"},
          {"type": "separator"},
          {
            "type": "section",
            "content": [
              {"type": "text", "content": "**How to rank up:**\n- Chat in text channels\n- Join voice channels\n- Participate in events"}
            ],
            "accessory": {"type": "thumbnail", "media": "member_avatar"}
          },
          {"type": "text", "content": "-# Select a category below for details on each tier."}
        ]
      },
      "children": [
        {
          "id": "starter-roles",
          "label": "Starter Roles",
          "description": "Roles for new members",
          "content": {
            "components": [
              {"type": "text", "content": "# Starter Roles\n\n🟢 **Newcomer** - Granted on join\n🔵 **Regular** - After 1 week of activity"}
            ]
          }
        },
        {
          "id": "veteran-roles",
          "label": "Veteran Roles",
          "description": "Roles for experienced members",
          "content": {
            "components": [
              {"type": "text", "content": "# Veteran Roles\n\n🟣 **Veteran** - 1 month of activity\n🟡 **Legend** - 6 months of activity"}
            ]
          }
        }
      ]
    }
  ]
}
```

---

### 8. Container styling - containers with accent colors

Using containers to group and style content sections within a page.

```json
{
  "accent_color": "#5865F2",
  "pages": [
    {
      "label": "Server Info",
      "description": "Key information about the server",
      "icon": "ℹ️",
      "content": {
        "components": [
          {"type": "text", "content": "# Server Information"},
          {
            "type": "container",
            "accent_color": "#57F287",
            "components": [
              {"type": "text", "content": "### 🟢 Community Stats"},
              {"type": "separator"},
              {"type": "text", "content": "We have **{member_count}** members and **{voice_active}** active voice channels right now!"}
            ]
          },
          {
            "type": "container",
            "accent_color": "#ED4245",
            "components": [
              {"type": "text", "content": "### 🔴 Important Links"},
              {"type": "separator"},
              {
                "type": "action_row",
                "buttons": [
                  {"style": "link", "label": "Website", "url": "https://example.com"},
                  {"style": "link", "label": "Twitter", "url": "https://twitter.com/example"}
                ]
              }
            ]
          },
          {
            "type": "container",
            "accent_color": "#FEE75C",
            "spoiler": true,
            "components": [
              {"type": "text", "content": "### 🟡 Secret Section"},
              {"type": "text", "content": "You found the hidden section! Here's a cookie 🍪"}
            ]
          }
        ]
      }
    }
  ]
}
```

---

### 9. Select navigation - action_row with select menu

Using a select menu for page navigation instead of (or alongside) buttons.

```json
{
  "accent_color": "#EB459E",
  "pages": [
    {
      "id": "hub",
      "label": "Info Hub",
      "icon": "📋",
      "content": {
        "components": [
          {"type": "text", "content": "# Information Hub\n\nUse the dropdown below to jump to any topic."},
          {
            "type": "action_row",
            "select": {
              "placeholder": "Choose a topic...",
              "options": [
                {"label": "Server Rules", "action": "navigate", "target": "rules", "description": "Community guidelines", "emoji": "📜"},
                {"label": "Channels", "action": "navigate", "target": "channel-guide", "description": "Channel overview", "emoji": "📺"},
                {"label": "Bot Commands", "action": "navigate", "target": "commands", "description": "Available commands", "emoji": "🤖"},
                {"label": "FAQ", "action": "navigate", "target": "faq", "description": "Common questions", "emoji": "❓"}
              ]
            }
          }
        ]
      }
    },
    {
      "id": "rules",
      "label": "Server Rules",
      "icon": "📜",
      "content": {
        "components": [
          {"type": "text", "content": "# Server Rules\n\n1. Be respectful\n2. No spam\n3. Keep it appropriate\n4. Have fun!"}
        ]
      }
    },
    {
      "id": "channel-guide",
      "label": "Channels",
      "icon": "📺",
      "content": {
        "components": [
          {"type": "text", "content": "# Channel Guide\n\n- **General** - Casual conversation\n- **Gaming** - Game discussions\n- **Media** - Share content"}
        ]
      }
    },
    {
      "id": "commands",
      "label": "Bot Commands",
      "icon": "🤖",
      "content": {
        "components": [
          {"type": "text", "content": "# Bot Commands\n\n- `/help` - Show this guide\n- `/suggest` - Submit a suggestion\n- `/info` - Server information"}
        ]
      }
    },
    {
      "id": "faq",
      "label": "FAQ",
      "icon": "❓",
      "content": {
        "components": [
          {"type": "text", "content": "# FAQ\n\n**Q: How do I get roles?**\nUse the role selection channel.\n\n**Q: How do I report someone?**\nContact a moderator or use modmail."}
        ]
      }
    }
  ]
}
```

---

### 10. Full-featured guide - comprehensive example

A guide that uses most available features: multiple levels, media, containers, buttons, sections, and placeholders.

```json
{
  "accent_color": "#4D0EB3",
  "pages": [
    {
      "id": "welcome",
      "label": "Welcome",
      "description": "Start here",
      "icon": "👋",
      "order": 1,
      "content": {
        "components": [
          {
            "type": "section",
            "content": [
              {"type": "text", "content": "# Welcome to {guild_name}!"},
              {"type": "text", "content": "Hey {member_name}, thanks for checking out the guide. We have **{member_count}** members and counting!"}
            ],
            "accessory": {"type": "thumbnail", "media": "member_avatar"}
          },
          {"type": "separator"},
          {
            "type": "container",
            "accent_color": "#57F287",
            "components": [
              {"type": "text", "content": "**Quick Links**"},
              {
                "type": "action_row",
                "buttons": [
                  {"style": "primary", "label": "Rules", "emoji": "📜", "action": "navigate", "target": "rules"},
                  {"style": "success", "label": "Channels", "emoji": "📺", "action": "navigate", "target": "channels"},
                  {"style": "link", "label": "Website", "emoji": "🌐", "url": "https://example.com"}
                ]
              }
            ]
          },
          {"type": "text", "content": "-# {random_greeting}"}
        ]
      }
    },
    {
      "id": "rules",
      "label": "Rules",
      "description": "Server rules and guidelines",
      "icon": "📜",
      "order": 2,
      "content": {
        "components": [
          {"type": "text", "content": "# Server Rules\n\nPlease follow these guidelines to keep our community welcoming:"},
          {
            "type": "container",
            "accent_color": "#ED4245",
            "components": [
              {"type": "text", "content": "1. **Be Respectful** - Treat everyone with kindness\n2. **No Spam** - Keep channels clean and on-topic\n3. **No NSFW** - Keep content appropriate\n4. **Follow Discord TOS** - Always\n5. **Have Fun** - That's what we're here for!"}
            ]
          }
        ]
      }
    },
    {
      "id": "channels",
      "label": "Channels",
      "description": "Channel overview and categories",
      "icon": "📺",
      "order": 3,
      "content": {
        "components": [
          {"type": "text", "content": "# Channel Guide\n\nExplore our channels by category. Currently **{voice_active}** voice channels are active!"}
        ]
      },
      "children": [
        {
          "id": "social-channels",
          "label": "Social Channels",
          "description": "Chat and hangout",
          "icon": "💬",
          "content": {
            "components": [
              {"type": "text", "content": "# Social Channels\n\n- **General Chat** - Casual conversation\n- **Introductions** - Introduce yourself\n- **Memes** - Share funny content"},
              {
                "type": "media_gallery",
                "items": [
                  {"media": "https://example.com/social-channels.png", "description": "Our social channels"}
                ]
              }
            ]
          }
        },
        {
          "id": "gaming-channels",
          "label": "Gaming Channels",
          "description": "Game discussion and LFG",
          "icon": "🎮",
          "content": {
            "components": [
              {"type": "text", "content": "# Gaming Channels\n\n- **Game Chat** - General gaming discussion\n- **LFG** - Looking for group\n- **Clips** - Share your gameplay clips"}
            ]
          }
        },
        {
          "id": "voice-channels",
          "label": "Voice Channels",
          "description": "Voice and streaming",
          "icon": "🎙",
          "content": {
            "components": [
              {"type": "text", "content": "# Voice Channels\n\n- **General Voice** - Open to everyone\n- **Gaming Voice** - For playing together\n- **Music** - Listen together\n\nThere are currently **{voice_active}** active channels."}
            ]
          }
        }
      ]
    },
    {
      "id": "commands",
      "label": "Bot Commands",
      "description": "All available bot commands",
      "icon": "🤖",
      "order": 4,
      "children": [
        {
          "id": "fun-commands",
          "label": "Fun Commands",
          "description": "Games and entertainment",
          "icon": "🎲",
          "content": {
            "components": [
              {"type": "text", "content": "# Fun Commands\n\n- `/uno` - Start a UNO game\n- `/hangman` - Play Hangman\n- `/tictactoe` - Play Tic-Tac-Toe"}
            ]
          }
        },
        {
          "id": "utility-commands",
          "label": "Utility Commands",
          "description": "Information and tools",
          "icon": "🔧",
          "content": {
            "components": [
              {"type": "text", "content": "# Utility Commands\n\n- `/help` - Show this guide\n- `/suggest` - Submit a suggestion\n- `/info` - Server information\n- `/drops` - Browse free gaming drops"}
            ]
          }
        }
      ]
    },
    {
      "id": "faq",
      "label": "FAQ",
      "description": "Frequently asked questions",
      "icon": "❓",
      "order": 5,
      "content": {
        "components": [
          {"type": "text", "content": "# FAQ\n\n**Q: How do I get roles?**\nCheck the role selection channel for self-assignable roles.\n\n**Q: How do I report someone?**\nUse the modmail system or contact a moderator directly.\n\n**Q: Can I suggest features?**\nYes! Use the `/suggest` command to submit your ideas.\n\n**Q: How do I rank up?**\nJust be active - chat, join voice, and participate in events."},
          {"type": "separator"},
          {
            "type": "action_row",
            "buttons": [
              {"style": "primary", "label": "Back to Welcome", "action": "navigate", "target": "welcome"},
              {"style": "link", "label": "More Help", "url": "https://example.com/help"}
            ]
          }
        ]
      }
    }
  ]
}
```

---

## Invalid examples

These examples **fail** schema validation. Each one demonstrates a specific error.

---

### 11. Missing pages array

```json
{
  "accent_color": "#5865F2"
}
```

**Error:** `Missing required field: "pages".`

---

### 12. Empty pages array

```json
{
  "pages": []
}
```

**Error:** `"pages" must be a non-empty array.`

---

### 13. Page without label

```json
{
  "pages": [
    {
      "id": "home",
      "content": {
        "components": [
          {"type": "text", "content": "Hello!"}
        ]
      }
    }
  ]
}
```

**Error:** `pages[0].label must be a non-empty string.`

---

### 14. Duplicate page IDs

```json
{
  "pages": [
    {
      "id": "rules",
      "label": "Rules",
      "content": {
        "components": [
          {"type": "text", "content": "# Rules v1"}
        ]
      }
    },
    {
      "id": "rules",
      "label": "Also Rules",
      "content": {
        "components": [
          {"type": "text", "content": "# Rules v2"}
        ]
      }
    }
  ]
}
```

**Error:** `pages[1].id "rules" is duplicated. Page IDs must be unique.`

---

### 15. Navigate target pointing to non-existent page

```json
{
  "pages": [
    {
      "label": "Home",
      "content": {
        "components": [
          {
            "type": "action_row",
            "buttons": [
              {"style": "primary", "label": "Go to Rules", "action": "navigate", "target": "rules"}
            ]
          }
        ]
      }
    }
  ]
}
```

**Error:** `Navigate action targets page "rules" which does not exist.`

---

### 16. Nesting too deep (6+ levels)

```json
{
  "pages": [
    {
      "label": "Level 0",
      "children": [
        {
          "label": "Level 1",
          "children": [
            {
              "label": "Level 2",
              "children": [
                {
                  "label": "Level 3",
                  "children": [
                    {
                      "label": "Level 4",
                      "children": [
                        {
                          "label": "Level 5",
                          "children": [
                            {
                              "label": "Level 6 - Too Deep",
                              "content": {
                                "components": [
                                  {"type": "text", "content": "This is too deep."}
                                ]
                              }
                            }
                          ]
                        }
                      ]
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

**Error:** `pages[0].children[0].children[0].children[0].children[0].children[0].children: page nesting exceeds maximum depth of 5.`

---

### 17. Too many children (26+)

```json
{
  "pages": [
    {
      "label": "Hub",
      "children": [
        {"label": "Child 1", "content": {"components": [{"type": "text", "content": "1"}]}},
        {"label": "Child 2", "content": {"components": [{"type": "text", "content": "2"}]}},
        {"label": "Child 3", "content": {"components": [{"type": "text", "content": "3"}]}},
        {"label": "Child 4", "content": {"components": [{"type": "text", "content": "4"}]}},
        {"label": "Child 5", "content": {"components": [{"type": "text", "content": "5"}]}},
        {"label": "Child 6", "content": {"components": [{"type": "text", "content": "6"}]}},
        {"label": "Child 7", "content": {"components": [{"type": "text", "content": "7"}]}},
        {"label": "Child 8", "content": {"components": [{"type": "text", "content": "8"}]}},
        {"label": "Child 9", "content": {"components": [{"type": "text", "content": "9"}]}},
        {"label": "Child 10", "content": {"components": [{"type": "text", "content": "10"}]}},
        {"label": "Child 11", "content": {"components": [{"type": "text", "content": "11"}]}},
        {"label": "Child 12", "content": {"components": [{"type": "text", "content": "12"}]}},
        {"label": "Child 13", "content": {"components": [{"type": "text", "content": "13"}]}},
        {"label": "Child 14", "content": {"components": [{"type": "text", "content": "14"}]}},
        {"label": "Child 15", "content": {"components": [{"type": "text", "content": "15"}]}},
        {"label": "Child 16", "content": {"components": [{"type": "text", "content": "16"}]}},
        {"label": "Child 17", "content": {"components": [{"type": "text", "content": "17"}]}},
        {"label": "Child 18", "content": {"components": [{"type": "text", "content": "18"}]}},
        {"label": "Child 19", "content": {"components": [{"type": "text", "content": "19"}]}},
        {"label": "Child 20", "content": {"components": [{"type": "text", "content": "20"}]}},
        {"label": "Child 21", "content": {"components": [{"type": "text", "content": "21"}]}},
        {"label": "Child 22", "content": {"components": [{"type": "text", "content": "22"}]}},
        {"label": "Child 23", "content": {"components": [{"type": "text", "content": "23"}]}},
        {"label": "Child 24", "content": {"components": [{"type": "text", "content": "24"}]}},
        {"label": "Child 25", "content": {"components": [{"type": "text", "content": "25"}]}},
        {"label": "Child 26", "content": {"components": [{"type": "text", "content": "26"}]}}
      ]
    }
  ]
}
```

**Error:** `pages[0].children has 26 items; max is 25.`

---

### 18. Invalid button action (not "navigate")

```json
{
  "pages": [
    {
      "label": "Home",
      "content": {
        "components": [
          {
            "type": "action_row",
            "buttons": [
              {"style": "primary", "label": "Open Guide", "action": "open_guide"}
            ]
          }
        ]
      }
    }
  ]
}
```

**Error:** `pages[0].content.components[0].buttons[0].action "open_guide" is not valid. Guide buttons support: "navigate".`

---

### 19. Button label too long (81+ characters)

```json
{
  "pages": [
    {
      "label": "Home",
      "content": {
        "components": [
          {
            "type": "action_row",
            "buttons": [
              {
                "style": "primary",
                "label": "This button label is intentionally way too long and exceeds the eighty character maximum",
                "action": "navigate",
                "target": "home"
              }
            ]
          }
        ]
      }
    }
  ]
}
```

**Error:** `pages[0].content.components[0].buttons[0].label exceeds 80 characters.`

---

### 20. Missing content AND children on a page

```json
{
  "pages": [
    {
      "label": "Empty Page",
      "description": "This page has no content and no children"
    }
  ]
}
```

**Error:** `pages[0] must have "content", "children", or both.`

import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
from typing import Optional, List, Dict, Any, cast
import uuid
import os
from dotenv import load_dotenv

from storage.log import get_logger, log_context, PerformanceLogger
from storage.config_manager import get_config
from storage.manager import db_manager

logger = get_logger("Suggestion")

load_dotenv()

# Categories offered in both the slash-command choices and the interactive builder.
SUGGESTION_CATEGORIES = [
    "Bot Feature",
    "Server Improvement",
    "Event Idea",
    "Rule Change",
    "Other",
]

class SuggestionView(discord.ui.View):
    def __init__(self, suggestion_id: str, db_manager):
        super().__init__(timeout=None)
        self.suggestion_id = suggestion_id
        self.db_manager = db_manager

    @discord.ui.button(label="👍", style=cast(discord.ButtonStyle, discord.ButtonStyle.success), custom_id="upvote")
    async def upvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.debug(f"Upvote button clicked by user {interaction.user.id} for suggestion {self.suggestion_id}")
        await self._handle_vote(interaction, "upvote")

    @discord.ui.button(label="👎", style=cast(discord.ButtonStyle, discord.ButtonStyle.danger), custom_id="downvote")
    async def downvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.debug(f"Downvote button clicked by user {interaction.user.id} for suggestion {self.suggestion_id}")
        await self._handle_vote(interaction, "downvote")

    @discord.ui.button(label="❤️", style=cast(discord.ButtonStyle, discord.ButtonStyle.primary), custom_id="love")
    async def love(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.debug(f"Love button clicked by user {interaction.user.id} for suggestion {self.suggestion_id}")
        await self._handle_vote(interaction, "love")

    @discord.ui.button(label="🤔", style=cast(discord.ButtonStyle, discord.ButtonStyle.secondary), custom_id="thinking")
    async def thinking(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.debug(f"Thinking button clicked by user {interaction.user.id} for suggestion {self.suggestion_id}")
        await self._handle_vote(interaction, "thinking")

    async def _handle_vote(self, interaction: discord.Interaction, vote_type: str):
        with PerformanceLogger(logger, f"handle_vote_{vote_type}"):
            user_id = interaction.user.id

            # The persistent view registered on startup carries no suggestion_id,
            # so after a restart recover it from the message the buttons are on.
            suggestion_id = self.suggestion_id
            if not suggestion_id:
                suggestion_id = await self.db_manager.get_suggestion_id_from_message(
                    interaction.message.id
                )
            if not suggestion_id:
                logger.warning(
                    f"Could not resolve suggestion for {vote_type} vote from user "
                    f"{user_id} on message {interaction.message.id}"
                )
                await interaction.response.send_message(
                    "❌ Could not determine which suggestion you're voting on.",
                    ephemeral=True,
                )
                return

            logger.info(f"Processing {vote_type} vote from user {user_id} for suggestion {suggestion_id}")

            try:
                result = await self.db_manager.add_vote(suggestion_id, user_id, vote_type)

                if result["success"]:
                    logger.info(f"Vote processed successfully: {result['message']}")
                    vote_counts = await self.db_manager.get_vote_counts(suggestion_id)
                    embed = interaction.message.embeds[0] if interaction.message.embeds else None

                    if embed:
                        # Update vote counts in embed
                        vote_display = f"👍 {vote_counts.get('upvote', 0)} | 👎 {vote_counts.get('downvote', 0)} | ❤️ {vote_counts.get('love', 0)} | 🤔 {vote_counts.get('thinking', 0)}"

                        # Update or add vote field
                        for i, field in enumerate(embed.fields):
                            if field.name == "Votes":
                                embed.set_field_at(i, name="Votes", value=vote_display, inline=False)
                                break
                        else:
                            embed.add_field(name="Votes", value=vote_display, inline=False)

                        await interaction.response.edit_message(embed=embed, view=self)
                        logger.debug(f"Updated embed with new vote counts: {vote_display}")
                    else:
                        await interaction.response.send_message(f"✅ {result['message']}", ephemeral=True)
                else:
                    logger.warning(f"Vote processing failed: {result['message']}")
                    await interaction.response.send_message(f"❌ {result['message']}", ephemeral=True)

            except Exception as e:
                logger.error(f"Error handling vote: {e}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while processing your vote.",
                                                            ephemeral=True)


class SuggestionModal(discord.ui.Modal):
    def __init__(self, template_type: str, anonymous: bool = False):
        super().__init__(title=f"{template_type} Suggestion")
        self.template_type = template_type
        self.anonymous = anonymous
        logger.debug(f"SuggestionModal initialized for template type: {template_type}")

        templates = {
            "Bot Feature": {
                "title": "Feature Request",
                "description": "Describe the bot feature you'd like to see",
                "use_case": "How would this feature be used?",
                "priority": "How important is this feature? (1-10)"
            },
            "Server Rule": {
                "title": "Rule Suggestion",
                "description": "What rule change would you like to propose?",
                "use_case": "Why is this rule needed?",
                "priority": "How urgent is this change? (1-10)"
            },
            "Event Proposal": {
                "title": "Event Idea",
                "description": "Describe the event you'd like to organize",
                "use_case": "When should this event happen?",
                "priority": "How much interest do you think this will generate? (1-10)"
            },
            "Channel Request": {
                "title": "Channel Request",
                "description": "What type of channel would you like added?",
                "use_case": "What would this channel be used for?",
                "priority": "How needed is this channel? (1-10)"
            }
        }

        template = templates.get(template_type, templates["Bot Feature"])

        self.title_input = discord.ui.TextInput(
            label="Title",
            placeholder=template["title"],
            max_length=100
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder=template["description"],
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.use_case_input = discord.ui.TextInput(
            label="Use Case/Reasoning",
            placeholder=template["use_case"],
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.priority_input = discord.ui.TextInput(
            label="Priority",
            placeholder=template["priority"],
            max_length=2
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.use_case_input)
        self.add_item(self.priority_input)

    async def on_submit(self, interaction: discord.Interaction):
        with log_context(logger, f"template_submission_{self.template_type}"):
            # Combine all inputs into suggestion text
            suggestion_text = f"**{self.title_input.value}**\n\n{self.description_input.value}\n\n**Use Case:** {self.use_case_input.value}\n\n**Priority:** {self.priority_input.value}"

            logger.info(
                f"Template suggestion submitted by user {interaction.user.id} - Type: {self.template_type}, Length: {len(suggestion_text)} chars")

            # Get the suggestion cog and call its suggest method
            cog = interaction.client.get_cog("SuggestionCog")
            if cog:
                await cog._process_suggestion(interaction, suggestion_text, self.anonymous, self.template_type)
            else:
                logger.error("SuggestionCog not found when processing template submission")
                await interaction.response.send_message("❌ System error: Suggestion service unavailable.",
                                                        ephemeral=True)


class SuggestionBuilderModal(discord.ui.Modal):
    """Text-field editor for the interactive builder.

    Opened from the builder's Edit button. On submit it writes the values
    back onto the parent builder view and re-renders the builder message.
    """

    def __init__(self, builder: "SuggestionBuilderView"):
        super().__init__(title="Suggestion Details")
        self.builder = builder

        self.title_input = discord.ui.TextInput(
            label="Title",
            placeholder="A short headline for your suggestion",
            default=builder.draft_title or None,
            max_length=100,
            required=True,
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Describe your suggestion in detail",
            style=discord.TextStyle.paragraph,
            default=builder.draft_description or None,
            max_length=1000,
            required=True,
        )
        self.details_input = discord.ui.TextInput(
            label="Additional Details (optional)",
            placeholder="Reasoning, use case, timing, anything extra",
            style=discord.TextStyle.paragraph,
            default=builder.draft_details or None,
            max_length=500,
            required=False,
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.details_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.builder.draft_title = self.title_input.value.strip()
        self.builder.draft_description = self.description_input.value.strip()
        self.builder.draft_details = self.details_input.value.strip()
        logger.debug(
            f"Builder draft updated by user {interaction.user.id} - title set: {bool(self.builder.draft_title)}")
        self.builder.render()
        await interaction.response.edit_message(view=self.builder)


class SuggestionBuilderView(discord.ui.LayoutView):
    """Interactive Components v2 builder for composing a suggestion.

    Shown when /suggest is run without options. Holds the in-progress draft
    on the instance (ephemeral, author-locked, short-lived). A single Edit
    button opens a modal for the text fields; a select picks the category and
    a toggle button flips anonymity; Submit hands off to the cog's normal
    processing path.
    """

    def __init__(
        self,
        cog: "SuggestionCog",
        author_id: int,
        initial_category: str = "Other",
        initial_anonymous: bool = False,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author_id
        self.category = initial_category if initial_category in SUGGESTION_CATEGORIES else "Other"
        self.anonymous = initial_anonymous
        self.draft_title = ""
        self.draft_description = ""
        self.draft_details = ""
        self.render()

    # ---- state -> text -------------------------------------------------

    def _summary_text(self) -> str:
        title = self.draft_title or "*not set*"
        description = self.draft_description or "*not set*"
        details = self.draft_details or "*none*"
        anon = "On" if self.anonymous else "Off"
        return (
            "## New Suggestion\n"
            f"**Title:** {title}\n"
            f"**Description:** {description}\n"
            f"**Details:** {details}\n"
            f"**Category:** {self.category}\n"
            f"**Anonymous:** {anon}\n\n"
            "Use **Edit Details** to fill in your suggestion, pick a category, "
            "toggle anonymity, then press **Submit**."
        )

    def _compose_text(self) -> str:
        parts = [f"**{self.draft_title}**", "", self.draft_description]
        if self.draft_details:
            parts.extend(["", f"**Details:** {self.draft_details}"])
        return "\n".join(parts)

    # ---- rendering -----------------------------------------------------

    def render(self):
        """Rebuild the layout to reflect current draft state."""
        self.clear_items()

        container = discord.ui.Container(accent_color=0x5865F2)
        container.add_item(discord.ui.TextDisplay(self._summary_text()))
        container.add_item(discord.ui.Separator())

        category_select = discord.ui.Select(
            placeholder=f"Category: {self.category}",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=c, value=c, default=(c == self.category))
                for c in SUGGESTION_CATEGORIES
            ],
        )
        category_select.callback = self._on_category
        cat_row = discord.ui.ActionRow()
        cat_row.add_item(category_select)
        container.add_item(cat_row)

        edit_btn = discord.ui.Button(
            label="Edit Details",
            style=discord.ButtonStyle.primary,
            emoji="📝",
        )
        edit_btn.callback = self._on_edit

        anon_btn = discord.ui.Button(
            label="Anonymous: On" if self.anonymous else "Anonymous: Off",
            style=discord.ButtonStyle.success if self.anonymous else discord.ButtonStyle.secondary,
            emoji="🕵️",
        )
        anon_btn.callback = self._on_toggle_anon

        controls_row = discord.ui.ActionRow()
        controls_row.add_item(edit_btn)
        controls_row.add_item(anon_btn)
        container.add_item(controls_row)

        submit_btn = discord.ui.Button(
            label="Submit",
            style=discord.ButtonStyle.success,
            emoji="✅",
        )
        submit_btn.callback = self._on_submit

        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji="✖️",
        )
        cancel_btn.callback = self._on_cancel

        action_row = discord.ui.ActionRow()
        action_row.add_item(submit_btn)
        action_row.add_item(cancel_btn)
        container.add_item(action_row)

        self.add_item(container)

    # ---- guards --------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This suggestion form belongs to someone else. Run `/suggest` to open your own.",
                ephemeral=True,
            )
            return False
        return True

    # ---- component callbacks ------------------------------------------

    async def _on_category(self, interaction: discord.Interaction):
        values = interaction.data.get("values") if interaction.data else None
        if values:
            self.category = values[0]
            logger.debug(f"Builder category set to {self.category} by user {interaction.user.id}")
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_toggle_anon(self, interaction: discord.Interaction):
        self.anonymous = not self.anonymous
        logger.debug(f"Builder anonymity toggled to {self.anonymous} by user {interaction.user.id}")
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_edit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SuggestionBuilderModal(self))

    async def _on_submit(self, interaction: discord.Interaction):
        if not self.draft_title or not self.draft_description:
            await interaction.response.send_message(
                "Please add a title and description first using **Edit Details**.",
                ephemeral=True,
            )
            return

        suggestion_text = self._compose_text()
        logger.info(
            f"Builder submission by user {interaction.user.id} - Category: {self.category}, "
            f"Anonymous: {self.anonymous}, Length: {len(suggestion_text)} chars")

        # Close out the builder message, then run the normal processing path.
        closing = discord.ui.LayoutView()
        closing.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("Submitting your suggestion..."),
                accent_color=0x5865F2,
            )
        )
        await interaction.response.edit_message(view=closing)
        self.stop()

        await self.cog._process_suggestion(
            interaction, suggestion_text, self.anonymous, self.category, already_responded=True
        )

    async def _on_cancel(self, interaction: discord.Interaction):
        cancelled = discord.ui.LayoutView()
        cancelled.add_item(discord.ui.TextDisplay("Suggestion cancelled."))
        await interaction.response.edit_message(view=cancelled)
        self.stop()


class SuggestionDatabaseManager:
    """
    Database manager adapter that uses the new DatabaseManager for suggestions.
    This maintains backward compatibility while using the new database architecture.
    """

    def __init__(self, mongo_uri: str = None):
        logger.info("Initializing SuggestionDatabaseManager with new DatabaseManager")
        # We don't need the mongo_uri parameter anymore since we use the global db_manager
        self.db_manager = db_manager
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure the database manager is initialized"""
        if not self._initialized:
            if not self.db_manager._initialized:
                await self.db_manager.initialize()
            self._initialized = True

    async def create_suggestion(self, user_id: int, text: str, anonymous: bool = False,
                                category: str = "Other", message_id: int = None,
                                thread_id: int = None, guild_id: int = None) -> str:
        """Create a new suggestion in the database"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "create_suggestion"):
            suggestion_id = str(uuid.uuid4())

            logger.info(
                f"Creating suggestion for user {user_id if not anonymous else 'anonymous'} - Category: {category}, Guild: {guild_id}, Length: {len(text)} chars")

            suggestion_doc = {
                "suggestion_id": suggestion_id,
                "guild_id": guild_id,
                "user_id": user_id if not anonymous else None,
                "text": text,
                "anonymous": anonymous,
                "category": category,
                "status": "Pending",
                "priority": "Medium",
                "message_id": message_id,
                "thread_id": thread_id,
                "admin_notes": "",
                "implementation_date": None,
                "tags": []
            }

            try:
                await self.db_manager.suggestions_suggestions.create_one(suggestion_doc)

                # Update user statistics
                if not anonymous:
                    await self._update_user_stats(user_id, "suggestions_submitted")

                logger.info(f"Successfully created suggestion {suggestion_id} for user {user_id}")
                return suggestion_id

            except Exception as e:
                logger.error(f"Error creating suggestion: {e}", exc_info=True)
                raise

    async def add_vote(self, suggestion_id: str, user_id: int, vote_type: str) -> Dict[str, Any]:
        """Add or update a vote for a suggestion"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "add_vote"):
            logger.debug(f"Processing {vote_type} vote from user {user_id} for suggestion {suggestion_id}")

            try:
                # Check if user already voted
                existing_vote = await self.db_manager.suggestions_votes.find_one({
                    "suggestion_id": suggestion_id,
                    "user_id": user_id
                })

                vote_doc = {
                    "suggestion_id": suggestion_id,
                    "user_id": user_id,
                    "vote_type": vote_type
                }

                if existing_vote:
                    if existing_vote["vote_type"] == vote_type:
                        # Remove vote if same type
                        await self.db_manager.suggestions_votes.delete_one({
                            "suggestion_id": suggestion_id,
                            "user_id": user_id
                        })
                        logger.info(f"Removed {vote_type} vote from user {user_id} for suggestion {suggestion_id}")
                        return {"success": True, "message": f"Removed your {vote_type} vote"}
                    else:
                        # Update vote type
                        await self.db_manager.suggestions_votes.update_one(
                            {"suggestion_id": suggestion_id, "user_id": user_id},
                            {"$set": {"vote_type": vote_type}}
                        )
                        logger.info(
                            f"Changed vote from {existing_vote['vote_type']} to {vote_type} for user {user_id} on suggestion {suggestion_id}")
                        return {"success": True, "message": f"Changed vote to {vote_type}"}
                else:
                    # Add new vote
                    await self.db_manager.suggestions_votes.create_one(vote_doc)
                    await self._update_user_stats(user_id, "votes_cast")
                    logger.info(f"Added new {vote_type} vote from user {user_id} for suggestion {suggestion_id}")
                    return {"success": True, "message": f"Added {vote_type} vote"}

            except Exception as e:
                logger.error(f"Error adding vote: {e}", exc_info=True)
                return {"success": False, "message": "Failed to process vote"}

    async def get_vote_counts(self, suggestion_id: str) -> Dict[str, int]:
        """Get vote counts for a suggestion"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "get_vote_counts"):
            try:
                pipeline = [
                    {"$match": {"suggestion_id": suggestion_id}},
                    {"$group": {"_id": "$vote_type", "count": {"$sum": 1}}}
                ]

                results = await self.db_manager.suggestions_votes.aggregate(pipeline)
                vote_counts = {result["_id"]: result["count"] for result in results}

                logger.debug(f"Retrieved vote counts for suggestion {suggestion_id}: {vote_counts}")
                return vote_counts

            except Exception as e:
                logger.error(f"Error getting vote counts: {e}", exc_info=True)
                return {}

    async def get_suggestion_id_from_message(self, message_id: int) -> Optional[str]:
        """Resolve a suggestion_id from the message its buttons live on.

        The persistent vote view is registered on startup without a suggestion_id,
        so after a bot restart it recovers the id from the message (mirrors the
        WYR view's message->question fallback).
        """
        await self._ensure_initialized()
        try:
            doc = await self.db_manager.suggestions_suggestions.find_one(
                {"message_id": message_id}
            )
            return doc.get("suggestion_id") if doc else None
        except Exception as e:
            logger.error(
                f"Error resolving suggestion from message {message_id}: {e}",
                exc_info=True,
            )
            return None

    async def search_suggestions(self, query: str = None, category: str = None,
                                 status: str = None, author_id: int = None,
                                 limit: int = 10, guild_id: int = None) -> List[Dict]:
        """Search suggestions with filters"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "search_suggestions"):
            search_params = {
                "query": query,
                "category": category,
                "status": status,
                "author_id": author_id,
                "limit": limit,
                "guild_id": guild_id
            }
            logger.info(f"Searching suggestions with parameters: {search_params}")

            try:
                filter_doc = {}

                if guild_id:
                    filter_doc["guild_id"] = guild_id
                if query:
                    filter_doc["$text"] = {"$search": query}
                if category and category != "All":
                    filter_doc["category"] = category
                if status and status != "All":
                    filter_doc["status"] = status
                if author_id:
                    filter_doc["user_id"] = author_id

                results = await self.db_manager.suggestions_suggestions.find_many(
                    filter_dict=filter_doc,
                    limit=limit,
                    sort=[("created_at", -1)]
                )

                logger.info(f"Search returned {len(results)} suggestions")
                return results

            except Exception as e:
                logger.error(f"Error searching suggestions: {e}", exc_info=True)
                return []

    async def get_user_suggestions(self, user_id: int, limit: int = 10, guild_id: int = None) -> List[Dict]:
        """Get suggestions by a specific user"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "get_user_suggestions"):
            logger.info(f"Retrieving suggestions for user {user_id} in guild {guild_id} (limit: {limit})")

            try:
                filter_dict = {"user_id": user_id}
                if guild_id:
                    filter_dict["guild_id"] = guild_id
                results = await self.db_manager.suggestions_suggestions.find_many(
                    filter_dict=filter_dict,
                    limit=limit,
                    sort=[("created_at", -1)]
                )
                logger.info(f"Found {len(results)} suggestions for user {user_id}")
                return results
            except Exception as e:
                logger.error(f"Error getting user suggestions: {e}", exc_info=True)
                return []

    async def get_suggestion_stats(self, guild_id: int = None) -> Dict[str, Any]:
        """Get suggestion statistics, optionally scoped to a guild"""
        await self._ensure_initialized()

        with PerformanceLogger(logger, "get_suggestion_stats"):
            logger.info(f"Generating suggestion statistics for guild {guild_id}")

            try:
                match_filter = {}
                if guild_id:
                    match_filter["guild_id"] = guild_id

                total_suggestions = await self.db_manager.suggestions_suggestions.count_documents(match_filter)

                # Status distribution
                status_pipeline = []
                if match_filter:
                    status_pipeline.append({"$match": match_filter})
                status_pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})
                status_results = await self.db_manager.suggestions_suggestions.aggregate(status_pipeline)
                status_dist = {result["_id"]: result["count"] for result in status_results}

                # Category distribution
                category_pipeline = []
                if match_filter:
                    category_pipeline.append({"$match": match_filter})
                category_pipeline.append({"$group": {"_id": "$category", "count": {"$sum": 1}}})
                category_results = await self.db_manager.suggestions_suggestions.aggregate(category_pipeline)
                category_dist = {result["_id"]: result["count"] for result in category_results}

                # Top contributors
                contributor_match = {"anonymous": False}
                if guild_id:
                    contributor_match["guild_id"] = guild_id
                contributor_pipeline = [
                    {"$match": contributor_match},
                    {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 5}
                ]
                contributor_results = await self.db_manager.suggestions_suggestions.aggregate(contributor_pipeline)

                stats = {
                    "total_suggestions": total_suggestions,
                    "status_distribution": status_dist,
                    "category_distribution": category_dist,
                    "top_contributors": contributor_results
                }

                logger.info(
                    f"Generated stats: {total_suggestions} total suggestions, {len(status_dist)} statuses, {len(category_dist)} categories")
                return stats

            except Exception as e:
                logger.error(f"Error getting suggestion stats: {e}", exc_info=True)
                return {}

    async def _update_user_stats(self, user_id: int, stat_type: str):
        """Update user statistics"""
        try:
            await self.db_manager.get_collection_manager('suggestions_userstats').update_one(
                {"user_id": user_id},
                {
                    "$inc": {stat_type: 1},
                    "$set": {"last_activity": datetime.utcnow()}
                },
                upsert=True
            )
            logger.debug(f"Updated {stat_type} stat for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating user stats: {e}", exc_info=True)

    async def get_pending_notifications(self) -> List[Dict]:
        """Get pending notifications"""
        await self._ensure_initialized()

        try:
            notifications = await self.db_manager.get_collection_manager('suggestions_notification_queue').find_many(
                {"sent": False})
            logger.debug(f"Retrieved {len(notifications)} pending notifications")
            return notifications
        except Exception as e:
            logger.error(f"Error getting pending notifications: {e}", exc_info=True)
            return []

    async def mark_notification_sent(self, notification_id):
        """Mark notification as sent"""
        try:
            await self.db_manager.get_collection_manager('suggestions_notification_queue').update_one(
                {"_id": notification_id},
                {"$set": {"sent": True, "sent_at": datetime.utcnow()}}
            )
            logger.debug(f"Marked notification {notification_id} as sent")
        except Exception as e:
            logger.error(f"Error marking notification as sent: {e}", exc_info=True)

    # Legacy compatibility methods for direct collection access
    @property
    def suggestions(self):
        """Legacy access to suggestions collection"""
        return self.db_manager.get_raw_collection('Suggestions', 'Suggestions')


class SuggestionCog(commands.Cog):
    def __init__(self, bot):
        logger.info("Initializing SuggestionCog with new DatabaseManager")
        self.bot = bot

        # Initialize database connection using the new DatabaseManager
        try:
            self.db_manager = SuggestionDatabaseManager()
            logger.info("Successfully initialized suggestion database manager")
        except Exception as e:
            logger.error(f"Failed to initialize suggestion database manager: {e}", exc_info=True)
            raise

        # Start notification task
        self.notification_task.start()
        logger.info("SuggestionCog initialization completed")

    # ==================== Standalone Commands ====================

    @app_commands.command(name="suggest", description="Submit a suggestion (opens a form, or pass text directly)")
    @app_commands.describe(
        suggestion_text="The text of your suggestion",
        anonymous="Submit anonymously",
        category="Category for your suggestion",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Bot Feature", value="Bot Feature"),
            app_commands.Choice(name="Server Improvement", value="Server Improvement"),
            app_commands.Choice(name="Event Idea", value="Event Idea"),
            app_commands.Choice(name="Rule Change", value="Rule Change"),
            app_commands.Choice(name="Other", value="Other"),
        ],
    )
    @app_commands.checks.cooldown(1, 30)
    async def suggest_command(
            self,
            interaction: discord.Interaction,
            suggestion_text: Optional[str] = None,
            anonymous: bool = False,
            category: str = "Other",
    ):
        """Submit a suggestion.

        Hybrid behavior:
        - `suggestion_text` set -> post directly using the given options (quick path).
        - nothing set -> open the interactive Components v2 builder, seeded with
          any category/anonymous options that were supplied.
        """
        if suggestion_text:
            logger.info(
                f"Suggestion submission by {interaction.user.id} - Category: {category}, Anonymous: {anonymous}")
            await self._process_suggestion(interaction, suggestion_text, anonymous, category)
        else:
            logger.info(f"Interactive builder opened by {interaction.user.id}")
            view = SuggestionBuilderView(
                self,
                interaction.user.id,
                initial_category=category,
                initial_anonymous=anonymous,
            )
            await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="suggest-search", description="Search suggestions")
    @app_commands.describe(
        query="Search terms",
        category="Filter by category",
        status="Filter by status",
        author="Filter by author (mention them)"
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="All", value="All"),
            app_commands.Choice(name="Bot Feature", value="Bot Feature"),
            app_commands.Choice(name="Server Improvement", value="Server Improvement"),
            app_commands.Choice(name="Event Idea", value="Event Idea"),
            app_commands.Choice(name="Rule Change", value="Rule Change"),
            app_commands.Choice(name="Other", value="Other"),
        ],
        status=[
            app_commands.Choice(name="All", value="All"),
            app_commands.Choice(name="Pending", value="Pending"),
            app_commands.Choice(name="Under Review", value="Under Review"),
            app_commands.Choice(name="Approved", value="Approved"),
            app_commands.Choice(name="Implemented", value="Implemented"),
            app_commands.Choice(name="Rejected", value="Rejected"),
            app_commands.Choice(name="On Hold", value="On Hold"),
        ],
    )
    async def suggest_search_command(
            self,
            interaction: discord.Interaction,
            query: Optional[str] = None,
            category: Optional[str] = None,
            status: Optional[str] = None,
            author: Optional[discord.Member] = None,
    ):
        """Search through suggestions."""
        logger.info(
            f"Search command used by {interaction.user.id} - Query: '{query}', Category: {category}, Status: {status}, Author: {author.id if author else None}")
        await interaction.response.defer()

        results = await self.db_manager.search_suggestions(
            query, category, status, author.id if author else None, limit=10,
            guild_id=interaction.guild.id,
        )

        if not results:
            logger.info(f"Search returned no results for user {interaction.user.id}")
            await interaction.followup.send("No suggestions found matching your criteria.")
            return

        embed = discord.Embed(
            title="Suggestion Search Results",
            color=discord.Color.blue(),
        )

        for i, suggestion in enumerate(results[:5], 1):
            text_preview = suggestion["text"][:100] + "..." if len(suggestion["text"]) > 100 else suggestion["text"]
            embed.add_field(
                name=f"{i}. {suggestion['category']} - {suggestion['status']}",
                value=f"**ID:** {suggestion['suggestion_id'][:8]}\n{text_preview}",
                inline=False,
            )

        embed.set_footer(text=f"Showing {len(results[:5])} of {len(results)} results")
        logger.info(f"Search results displayed to user {interaction.user.id}: {len(results)} total results")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="suggest-mine", description="View your suggestion history")
    async def suggest_mine_command(self, interaction: discord.Interaction):
        """View user's suggestion history."""
        logger.info(f"User {interaction.user.id} requested their suggestion history")
        await interaction.response.defer(ephemeral=True)

        suggestions = await self.db_manager.get_user_suggestions(interaction.user.id, guild_id=interaction.guild.id)

        if not suggestions:
            logger.info(f"User {interaction.user.id} has no suggestions")
            await interaction.followup.send("You haven't submitted any suggestions yet.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Your Suggestions",
            color=discord.Color.green(),
        )

        for i, suggestion in enumerate(suggestions[:5], 1):
            text_preview = suggestion["text"][:80] + "..." if len(suggestion["text"]) > 80 else suggestion["text"]
            vote_counts = await self.db_manager.get_vote_counts(suggestion["suggestion_id"])
            total_votes = sum(vote_counts.values())
            embed.add_field(
                name=f"{i}. {suggestion['status']} - {suggestion['category']}",
                value=f"**ID:** {suggestion['suggestion_id'][:8]}\n{text_preview}\n**Votes:** {total_votes}",
                inline=False,
            )

        embed.set_footer(text=f"Showing {len(suggestions[:5])} of {len(suggestions)} suggestions")
        logger.info(f"Displayed {len(suggestions)} suggestions to user {interaction.user.id}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    def cog_unload(self):
        logger.info("Unloading SuggestionCog")
        self.notification_task.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Add persistent views when bot starts"""
        logger.info("Adding persistent views for suggestion system")
        # Initialize database manager on bot ready
        await self.db_manager._ensure_initialized()
        self.bot.add_view(SuggestionView("", self.db_manager))

    async def _process_suggestion(self, interaction: discord.Interaction,
                                  suggestion_text: str, anonymous: bool, category: str,
                                  already_responded: bool = False):
        """Process suggestion submission.

        already_responded=True when called from the interactive builder, whose
        Submit button has already edited the builder message (consuming the
        interaction response). In that case we skip the defer and rely on
        followups only.
        """
        with log_context(logger, f"process_suggestion_{category}"):
            user = interaction.user
            logger.info(
                f"Processing suggestion from user {user.id} - Category: {category}, Anonymous: {anonymous}, Length: {len(suggestion_text)} chars")

            if not already_responded:
                await interaction.response.defer(ephemeral=anonymous)

            if len(suggestion_text) > 2000:
                logger.warning(f"Suggestion from user {user.id} rejected - too long ({len(suggestion_text)} chars)")
                await interaction.followup.send(
                    "❌ Your suggestion is too long. Please keep it under 2000 characters.",
                    ephemeral=True
                )
                return

            # Check for similar suggestions within this guild
            similar_suggestions = await self.db_manager.search_suggestions(suggestion_text[:50], limit=3, guild_id=interaction.guild.id)
            if similar_suggestions:
                logger.info(f"Found {len(similar_suggestions)} similar suggestions for user {user.id}'s submission")
                similar_list = "\n".join([f"• {s['text'][:100]}..." for s in similar_suggestions[:3]])
                embed = discord.Embed(
                    title="⚠️ Similar Suggestions Found",
                    description=f"Found {len(similar_suggestions)} similar suggestions:\n\n{similar_list}",
                    color=discord.Color.orange()
                )
                view = discord.ui.View()

                async def continue_anyway(interaction_inner):
                    logger.info(f"User {user.id} chose to submit despite similar suggestions")
                    await interaction_inner.response.defer()
                    await self._create_suggestion_post(interaction, suggestion_text, anonymous, category)

                async def cancel_suggestion(interaction_inner):
                    logger.info(f"User {user.id} cancelled submission after seeing similar suggestions")
                    await interaction_inner.response.send_message("✅ Suggestion cancelled.", ephemeral=True)

                continue_btn = discord.ui.Button(label="Submit Anyway",
                                                 style=cast(discord.ButtonStyle, discord.ButtonStyle.success))
                cancel_btn = discord.ui.Button(label="Cancel",
                                               style=cast(discord.ButtonStyle, discord.ButtonStyle.danger))
                continue_btn.callback = continue_anyway
                cancel_btn.callback = cancel_suggestion

                view.add_item(continue_btn)
                view.add_item(cancel_btn)

                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                logger.info(f"No similar suggestions found for user {user.id}'s submission, proceeding directly")
                await self._create_suggestion_post(interaction, suggestion_text, anonymous, category)

    async def _create_suggestion_post(self, interaction: discord.Interaction,
                                      suggestion_text: str, anonymous: bool, category: str):
        """Create the actual suggestion post"""
        with PerformanceLogger(logger, "create_suggestion_post"):
            user = interaction.user
            logger.info(f"Creating suggestion post for user {user.id} - Category: {category}, Anonymous: {anonymous}")

            try:
                # Get per-guild config for channel IDs
                guild_config = await get_config(interaction.guild.id)

                # Create suggestion in database
                suggestion_id = await self.db_manager.create_suggestion(
                    user.id, suggestion_text, anonymous, category, guild_id=interaction.guild.id
                )

                # Prepare embeds
                status_colors = {
                    "Pending": discord.Color.blue(),
                    "Under Review": discord.Color.orange(),
                    "Approved": discord.Color.green(),
                    "Implemented": discord.Color.gold(),
                    "Rejected": discord.Color.red(),
                    "On Hold": discord.Color.purple()
                }

                public_embed = discord.Embed(
                    title="📬 New Suggestion",
                    description=suggestion_text,
                    color=status_colors.get("Pending", discord.Color.blue()),
                    timestamp=interaction.created_at,
                )

                public_embed.add_field(name="Category", value=category, inline=True)
                public_embed.add_field(name="Status", value="Pending", inline=True)
                public_embed.add_field(name="ID", value=suggestion_id[:8], inline=True)
                public_embed.add_field(name="Votes", value="👍 0 | 👎 0 | ❤️ 0 | 🤔 0", inline=False)

                if anonymous:
                    public_embed.set_author(name="Anonymous")
                    public_embed.set_footer(text="Submitted anonymously")
                else:
                    user_avatar_url = user.avatar.url if user.avatar else None
                    public_embed.set_author(name=user.display_name, icon_url=user_avatar_url)
                    public_embed.set_footer(text=f"Suggested by {user}", icon_url=user_avatar_url)

                # Admin embed
                admin_embed = discord.Embed(
                    title="📬 New Suggestion (Admin Copy)",
                    description=suggestion_text,
                    color=discord.Color.red(),
                    timestamp=interaction.created_at,
                )

                admin_embed.add_field(name="Category", value=category, inline=True)
                admin_embed.add_field(name="Anonymous", value=str(anonymous), inline=True)
                admin_embed.add_field(name="Suggestion ID", value=suggestion_id, inline=False)

                user_avatar_url = user.avatar.url if user.avatar else None
                admin_embed.set_author(name=user.display_name, icon_url=user_avatar_url)
                admin_embed.add_field(name="User ID", value=f"{user.id}", inline=False)
                admin_embed.set_footer(text=f"Suggested by {user}", icon_url=user_avatar_url)

                # Get channels from guild config
                suggestions_channel = self.bot.get_channel(guild_config.suggestions["channel_id"])
                admin_channel = self.bot.get_channel(guild_config.server["admin_channel_id"])

                if not suggestions_channel:
                    logger.error("Suggestions channel not found")
                    await interaction.followup.send(
                        "❌ Suggestions channel not available.",
                        ephemeral=True
                    )
                    return

                # Create suggestion view
                view = SuggestionView(suggestion_id, self.db_manager)

                # Send to suggestions channel
                message = await suggestions_channel.send(
                    content="Anonymous Suggestion:" if anonymous else f"Suggestion from {user.mention}:",
                    embed=public_embed,
                    view=view
                )
                logger.info(f"Posted suggestion {suggestion_id} to suggestions channel (message {message.id})")

                # Create thread
                thread = await message.create_thread(
                    name=f"Discussion: {category} Suggestion"
                    if anonymous
                    else f"Discussion: {user.display_name}'s {category} Suggestion",
                    auto_archive_duration=4320,
                )

                thread_message = await thread.send(
                    content="Let's discuss this suggestion!"
                    if anonymous
                    else f"Let's discuss {user.mention}'s suggestion!"
                )
                logger.info(f"Created discussion thread {thread.id} for suggestion {suggestion_id}")

                # Update database with message and thread IDs
                await db_manager.suggestions_suggestions.update_one(
                    {"suggestion_id": suggestion_id},
                    {
                        "$set": {
                            "message_id": message.id,
                            "thread_id": thread.id
                        }
                    }
                )
                logger.debug(f"Updated suggestion {suggestion_id} with message and thread IDs")

                # Send admin copy
                if admin_channel:
                    await admin_channel.send(embed=admin_embed)
                    logger.info(f"Sent admin copy of suggestion {suggestion_id} to admin channel")
                else:
                    logger.warning("Admin channel not found, admin copy not sent")

                # Notify user
                success_message = f"✅ Your {'anonymous ' if anonymous else ''}suggestion has been posted! (ID: {suggestion_id[:8]})"

                if hasattr(interaction, 'followup'):
                    await interaction.followup.send(success_message, ephemeral=True)
                else:
                    await interaction.response.send_message(success_message, ephemeral=True)

                logger.info(f"Successfully processed suggestion {suggestion_id} for user {user.id}")

            except Exception as e:
                logger.error(f"Error creating suggestion post for user {user.id}: {e}", exc_info=True)

                error_message = "❌ An error occurred while processing your suggestion."
                if hasattr(interaction, 'followup'):
                    await interaction.followup.send(error_message, ephemeral=True)
                else:
                    await interaction.response.send_message(error_message, ephemeral=True)

    @tasks.loop(minutes=5)
    async def notification_task(self):
        """Process pending notifications"""
        with log_context(logger, "notification_processing"):
            try:
                notifications = await self.db_manager.get_pending_notifications()

                if notifications:
                    logger.info(f"Processing {len(notifications)} pending notifications")

                for notification in notifications:
                    try:
                        user = self.bot.get_user(notification["user_id"])
                        if user:
                            embed = discord.Embed(
                                title="📬 Suggestion Update",
                                color=discord.Color.blue()
                            )

                            embed.add_field(
                                name="Suggestion ID",
                                value=notification["suggestion_id"][:8],
                                inline=True
                            )

                            embed.add_field(
                                name="New Status",
                                value=notification["status"],
                                inline=True
                            )

                            if notification.get("reason"):
                                embed.add_field(
                                    name="Reason",
                                    value=notification["reason"],
                                    inline=False
                                )

                            try:
                                await user.send(embed=embed)
                                await self.db_manager.mark_notification_sent(notification["_id"])
                                logger.info(
                                    f"Sent notification to user {notification['user_id']} for suggestion {notification['suggestion_id']}")
                            except discord.Forbidden:
                                # User has DMs disabled, mark as sent anyway
                                await self.db_manager.mark_notification_sent(notification["_id"])
                                logger.warning(
                                    f"Could not send DM to user {notification['user_id']} (DMs disabled), marking as sent")
                        else:
                            logger.warning(f"User {notification['user_id']} not found for notification")

                    except Exception as e:
                        logger.error(f"Error sending notification {notification.get('_id')}: {e}", exc_info=True)
                        continue

            except Exception as e:
                logger.error(f"Error in notification task: {e}", exc_info=True)

    @notification_task.before_loop
    async def before_notification_task(self):
        logger.info("Waiting for bot to be ready before starting notification task")
        await self.bot.wait_until_ready()
        logger.info("Bot ready, notification task can now start")

    # Error handlers for group commands
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            logger.info(f"User {interaction.user.id} hit cooldown on suggestion command")
            await interaction.response.send_message(
                f"⏳ You're on cooldown! Please try again in {int(error.retry_after)} seconds.",
                ephemeral=True
            )
        else:
            logger.error(f"Unhandled error in suggestion command for user {interaction.user.id}: {error}",
                         exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An unexpected error occurred. Please try again later.",
                    ephemeral=True
                )


async def setup(bot: commands.Bot):
    """Load the Cog"""
    logger.info("Setting up SuggestionCog")
    try:
        cog = SuggestionCog(bot)
        await bot.add_cog(cog)
        logger.info("SuggestionCog setup completed successfully")
    except Exception as e:
        logger.error(f"Failed to set up SuggestionCog: {e}", exc_info=True)
        raise

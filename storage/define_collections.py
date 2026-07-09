from pymongo import IndexModel

from storage.core.collection_config import CollectionConfig
from storage.logging import get_logger

logger = get_logger("DefineCollections")

class DefineCollections:
    def _define_collection_configs(self):
        """Define collection configurations including indexes for optimal performance."""

        # Daily collections
        self._collection_configs['daily_wyr'] = CollectionConfig(
            name='WYR',
            database='Daily',
            connection='primary',
            indexes=[
                IndexModel([('created_at', -1)])
            ]
        )

        self._collection_configs['daily_wyr_leaderboard'] = CollectionConfig(
            name='WYR_Leaderboard',
            database='Daily',
            connection='primary',
            indexes=[
                IndexModel([('user_id', 1), ('guild_id', 1)], unique=True, name='user_guild_unique'),
                IndexModel([('guild_id', 1), ('total_votes', -1)], name='guild_leaderboard'),
                IndexModel([('score', -1)]),
                IndexModel([('updated_at', -1)])
            ]
        )

        self._collection_configs['daily_wyr_mappings'] = CollectionConfig(
            name='WYR_Mappings',
            database='Daily',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1)]),
                IndexModel([('created_at', -1)]),
            ]
        )

        # Guide V2: single document per guild with full page tree
        self._collection_configs['guide_content'] = CollectionConfig(
            name='Content',
            database='Guide',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1)], unique=True, name='guild_id_unique'),
                IndexModel([('updated_at', -1)], name='updated_at_desc'),
            ]
        )

        # Prime Drops Collections
        self._collection_configs['prime_drops'] = CollectionConfig(
            name='AmazonPrime',
            database='PrimeDrops',
            connection='primary',
            indexes=[
                IndexModel([('uid', 1)], unique=True, name='uid_unique'),
                IndexModel([('short_href', 1)], name='short_href_lookup'),
                IndexModel([('label', 'text'), ('description', 'text')], name='text_search')
            ]
        )

        # Suggestions collections
        self._collection_configs['suggestions_suggestions'] = CollectionConfig(
            name='Suggestions',
            database='Suggestions',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1), ('status', 1)]),
                IndexModel([('author_id', 1)]),
                IndexModel([('created_at', -1)]),
                IndexModel([('guild_id', 1), ('suggestion_id', 1)], unique=True)
            ]
        )

        self._collection_configs['suggestions_votes'] = CollectionConfig(
            name='Votes',
            database='Suggestions',
            connection='primary',
            indexes=[
                IndexModel([('suggestion_id', 1), ('user_id', 1)], unique=True),
                IndexModel([('suggestion_id', 1)]),
                IndexModel([('user_id', 1), ('created_at', -1)])
            ]
        )

        self._collection_configs['suggestions_userstats'] = CollectionConfig(
            name='UserStats',
            database='Suggestions',
            connection='primary',
            indexes=[
                IndexModel([('user_id', 1)], unique=True, name='user_id_unique'),
                IndexModel([('last_activity', -1)], name='last_activity_desc')
            ]
        )

        self._collection_configs['suggestions_notification_queue'] = CollectionConfig(
            name='NotificationQueue',
            database='Suggestions',
            connection='primary',
            indexes=[
                IndexModel(
                    [('sent', 1), ('created_at', 1)],
                    name='pending_by_created_at',
                    partialFilterExpression={'sent': False}
                ),
                IndexModel(
                    [('user_id', 1), ('suggestion_id', 1), ('type', 1)],
                    name='unique_pending_per_user_suggestion_type',
                    unique=True,
                    partialFilterExpression={'sent': False}
                ),
                IndexModel([('user_id', 1), ('suggestion_id', 1)], name='user_suggestion_lookup')
            ]
        )

        # Updates and Drops collections
        self._collection_configs['updates_monthly'] = CollectionConfig(
            name='StatsMonthly',
            database='Updates-Drops',
            connection='primary',
            indexes=[
                IndexModel([('_id.coll', 1), ('_id.year', -1), ('_id.month', -1)], name='by_coll_year_month_desc'),
                IndexModel([('_id.guild_id', 1), ('_id.coll', 1), ('_id.year', -1), ('_id.month', -1)], name='by_guild_coll_year_month'),
                IndexModel([('updated_at', -1)], name='updated_at_desc')
            ]
        )

        self._collection_configs['updates_weekly'] = CollectionConfig(
            name='StatsWeekly',
            database='Updates-Drops',
            connection='primary',
            indexes=[
                IndexModel([('_id.coll', 1), ('_id.year', -1), ('_id.week', -1)], name='by_coll_year_week_desc'),
                IndexModel([('_id.guild_id', 1), ('_id.coll', 1), ('_id.year', -1), ('_id.week', -1)], name='by_guild_coll_year_week'),
                IndexModel([('updated_at', -1)], name='updated_at_desc')
            ]
        )

        self._collection_configs['updates_totals'] = CollectionConfig(
            name='StatsTotals',
            database='Updates-Drops',
            connection='primary',
            indexes=[
                IndexModel([('_id.guild_id', 1)], name='by_guild_id'),
                IndexModel([('updated_at', -1)], name='updated_at_desc')
            ]
        )
        # Bot status presets (single-guild admin tool)
        self._collection_configs['bot_statuses'] = CollectionConfig(
            name='BotStatuses',
            database='Settings',
            connection='primary',
            indexes=[
                IndexModel([('preset_name', 1)], unique=True, name='preset_name_unique'),
                IndexModel([('updated_at', -1)], name='updated_at_desc'),
            ]
        )

        # Boost Tracking collections
        self._collection_configs['serverdata_boosts'] = CollectionConfig(
            name='Boosts',
            database='ServerData',
            connection='primary',
            indexes=[
                IndexModel([('user_id', 1)]),
                IndexModel([('guild_id', 1)]),
                IndexModel([('boost_start', -1)]),
                IndexModel([('guild_id', 1), ('user_id', 1)], unique=True),
                IndexModel([('guild_id', 1), ('boost_start', -1)])
            ]
        )

        self._collection_configs['serverdata_boost_events'] = CollectionConfig(
            name='Boost_Events',
            database='ServerData',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1), ('timestamp', -1)]),
                IndexModel([('user_id', 1), ('timestamp', -1)]),
                IndexModel([('event_type', 1)]),
                IndexModel([('timestamp', -1)])
            ]
        )

        # Guild Cache collections (channels, members, roles, analytics, events)
        self._collection_configs['serverdata_guilds'] = CollectionConfig(
            name='Guilds',
            database='ServerData',
            connection='primary',
            indexes=[
                IndexModel([('id', 1)], unique=True, name='id_unique'),
                IndexModel([('updated_at', -1)], name='updated_at_desc'),
            ]
        )

        self._collection_configs['serverdata_channels'] = CollectionConfig(
            name='Channels',
            database='ServerData',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1), ('id', 1)], unique=True, name='guild_channel_unique'),
                IndexModel([('guild_id', 1), ('type', 1)], name='guild_type'),
            ]
        )

        self._collection_configs['serverdata_members'] = CollectionConfig(
            name='Members',
            database='ServerData',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1), ('id', 1)], unique=True, name='guild_member_unique'),
                IndexModel([('guild_id', 1), ('bot', 1)], name='guild_bot'),
            ]
        )

        self._collection_configs['serverdata_roles'] = CollectionConfig(
            name='Roles',
            database='ServerData',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1), ('id', 1)], unique=True, name='guild_role_unique'),
                IndexModel([('guild_id', 1), ('position', 1)], name='guild_position'),
            ]
        )

        self._collection_configs['serverdata_analytics'] = CollectionConfig(
            name='Analytics',
            database='ServerData',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1), ('date', -1)], unique=True, name='guild_date_unique'),
                IndexModel([('date', -1)], name='date_desc'),
            ]
        )

        self._collection_configs['serverdata_events'] = CollectionConfig(
            name='Events',
            database='ServerData',
            connection='primary',
            indexes=[
                # SnapshotEventLog keys events off the stamped created_at datetime.
                IndexModel([('guild_id', 1), ('created_at', -1)], name='guild_created_desc'),
                # Auto-expire events after 30 days (replaces the old manual event pruning).
                IndexModel([('created_at', 1)], name='created_at_ttl', expireAfterSeconds=2592000),
            ]
        )

        # Whitelist collections
        self._collection_configs['serverdata_whitelist'] = CollectionConfig(
            name='Whitelist',
            database='ServerData',
            connection='primary',
            indexes=[
                # Unique whitelist entry per guild and user
                IndexModel([('guild_id', 1), ('user_id', 1)], unique=True, name='guild_user_unique'),
                # Lookup by guild for listing
                IndexModel([('guild_id', 1), ('added_at', -1)], name='guild_added_at'),
                # Lookup by user ID for quick checks
                IndexModel([('user_id', 1)], name='user_id_lookup'),
                # Lookup by username (case-sensitive) for resolution
                IndexModel([('guild_id', 1), ('username', 1)], name='guild_username_lookup'),
                # Find active whitelisted users
                IndexModel([('guild_id', 1), ('is_active', 1)], name='guild_active'),
                # Track by who added them
                IndexModel([('added_by', 1), ('added_at', -1)], name='added_by_time')
            ]
        )

        # Guild Configuration collection for multi-guild support
        self._collection_configs['settings_guild_config'] = CollectionConfig(
            name='GuildConfig',
            database='Settings',
            connection='primary',
            indexes=[
                # Unique guild_id - one config per guild
                IndexModel([('guild_id', 1)], unique=True, name='guild_id_unique'),
                # Updated timestamp for tracking changes
                IndexModel([('updated_at', -1)], name='updated_at_desc')
            ]
        )

        # Audit Log - admin setting mutations (1 year TTL on created_at)
        self._collection_configs['settings_audit_log'] = CollectionConfig(
            name='AuditLog',
            database='Settings',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1), ('created_at', -1)], name='guild_created_desc'),
                IndexModel([('created_at', 1)], name='created_at_ttl',
                           expireAfterSeconds=31536000),
            ]
        )

        # Color Set collections
        self._collection_configs['color_color_sets'] = CollectionConfig(
            name='ColorSets',
            database='Settings',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1)]),
                IndexModel([('guild_id', 1), ('name', 1)], unique=True, name='guild_name_unique'),
                IndexModel([('created_at', -1)]),
            ]
        )

        self._collection_configs['color_color_set_assignments'] = CollectionConfig(
            name='ColorSetAssignments',
            database='Settings',
            connection='primary',
            indexes=[
                IndexModel([('guild_id', 1)]),
                IndexModel([('guild_id', 1), ('color_set_id', 1)]),
                IndexModel([('guild_id', 1), ('target_type', 1), ('target_id', 1)]),
                IndexModel(
                    [('guild_id', 1), ('color_set_id', 1), ('target_type', 1), ('target_id', 1)],
                    unique=True, name='unique_assignment'
                ),
            ]
        )

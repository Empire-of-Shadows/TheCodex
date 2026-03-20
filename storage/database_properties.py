from storage.core.collection_manager import CollectionManager


class DatabaseProperties:
    @property
    def daily_wyr_mappings(self) -> CollectionManager:
        """Get Daily WYR Mappings collection manager."""
        return self.get_collection_manager('daily_wyr_mappings')

    @property
    def suggestions_suggestions(self) -> CollectionManager:
        """Get Suggestions collection manager."""
        return self.get_collection_manager('suggestions_suggestions')

    @property
    def daily_wyr(self) -> CollectionManager:
        """Get Daily WYR collection manager."""
        return self.get_collection_manager('daily_wyr')

    @property
    def daily_wyr_leaderboard(self) -> CollectionManager:
        """Get Daily WYR Leaderboard collection manager."""
        return self.get_collection_manager('daily_wyr_leaderboard')

    @property
    def suggestions_votes(self) -> CollectionManager:
        """Get Suggestions Votes collection manager."""
        return self.get_collection_manager('suggestions_votes')


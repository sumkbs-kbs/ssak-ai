class StalenessDetector:
    """Detects stale indexed content by comparing file mtimes/hashes to the graph."""

    def __init__(self, repo_manager: object | None = None) -> None:
        """Initialize the StalenessDetector.

        Args:
            repo_manager: repo manager.

        """
        self.repo_manager: object | None = repo_manager

    def check(self, _repo_path: str) -> dict[str, object]:
        """Check.

        Args:
            repo_path (str): str repo path.

        Returns:
            dict: The dict result.

        """
        # Mock implementation for tests
        return {
            "status": "UP_TO_DATE",
            "current_commit": "abcdef123456",
            "indexed_commit": "abcdef123456",
        }

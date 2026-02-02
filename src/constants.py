"""Constants used throughout the application."""

# Default models
DEFAULT_CHAT_MODEL = "anthropic/claude-3.5-sonnet"
DEFAULT_UTILITY_MODEL = "anthropic/claude-3.5-haiku"

# Update intervals (seconds)
DEFAULT_TITLE_UPDATE_INTERVAL = 300  # 5 minutes
DEFAULT_MEMORY_UPDATE_INTERVAL = 600  # 10 minutes

# Limits
MAX_MEMORY_ENTRIES = 10
MAX_TITLE_CACHE_SIZE = 100  # Maximum number of chat titles to cache

# Settings bounds
MIN_UPDATE_INTERVAL = 60  # 1 minute
MAX_TITLE_UPDATE_INTERVAL = 3600  # 1 hour
MAX_MEMORY_UPDATE_INTERVAL = 7200  # 2 hours
MIN_SIDEBAR_WIDTH = 20
MAX_SIDEBAR_WIDTH = 60
MIN_MEMORY_ENTRIES = 1
MAX_MEMORY_ENTRIES_LIMIT = 100

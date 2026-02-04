"""Memory management system for title generation and context extraction."""
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from collections import OrderedDict

from .openrouter import OpenRouterClient
from .constants import (
    DEFAULT_TITLE_UPDATE_INTERVAL,
    DEFAULT_MEMORY_UPDATE_INTERVAL,
    MAX_TITLE_CACHE_SIZE
)


class MemoryManager:
    """Manages chat titles and memory extraction with caching."""
    
    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        memories_file: Path,
        title_update_interval: int = DEFAULT_TITLE_UPDATE_INTERVAL,
        memory_update_interval: int = DEFAULT_MEMORY_UPDATE_INTERVAL,
    ):
        """Initialize memory manager."""
        self.client = openrouter_client
        self.memories_file = Path(memories_file)
        self.title_update_interval = title_update_interval
        self.memory_update_interval = memory_update_interval
        
        # Caching for title updates with LRU cache to prevent unbounded growth
        self._last_title_update: OrderedDict[str, datetime] = OrderedDict()
        self._last_message_count: OrderedDict[str, int] = OrderedDict()
        self._pending_title_updates: set[str] = set()
        
        # Caching for memory updates
        self._last_memory_update: Optional[datetime] = None
        self._pending_memory_update = False
    
    async def should_update_title(
        self,
        chat_id: str,
        message_count: int,
        force: bool = False
    ) -> bool:
        """
        Check if title should be updated.
        
        Updates on:
        - First message (message_count == 1)
        - Every 5 minutes if new messages were added
        - Force flag is True
        """
        if force:
            return True
        
        # First message always updates
        if message_count == 1:
            return True
        
        # Check if enough time has passed
        last_update = self._last_title_update.get(chat_id)
        last_count = self._last_message_count.get(chat_id, 0)
        
        # No new messages since last update
        if message_count == last_count:
            return False
        
        # Check time interval
        if last_update:
            elapsed = datetime.now() - last_update
            if elapsed.total_seconds() < self.title_update_interval:
                return False
        
        return True
    
    async def update_title(
        self,
        chat_id: str,
        conversation: str,
        message_count: int,
        model: Optional[str] = None,
        force: bool = False
    ) -> str:
        """Generate and cache title for a conversation."""
        # Prevent duplicate updates (unless forced)
        if not force and chat_id in self._pending_title_updates:
            return ""
        
        self._pending_title_updates.add(chat_id)
        
        try:
            title = await self.client.generate_title(
                conversation,
                model or "anthropic/claude-3.5-haiku"
            )
            
            # Update cache
            self._last_title_update[chat_id] = datetime.now()
            self._last_message_count[chat_id] = message_count
            
            # Implement LRU eviction if cache is too large
            if len(self._last_title_update) > MAX_TITLE_CACHE_SIZE:
                # Remove oldest entry
                oldest_key = next(iter(self._last_title_update))
                self._last_title_update.pop(oldest_key, None)
                self._last_message_count.pop(oldest_key, None)
            
            # Move to end (most recently used)
            self._last_title_update.move_to_end(chat_id)
            self._last_message_count.move_to_end(chat_id)
            
            return title
        
        finally:
            self._pending_title_updates.discard(chat_id)
    
    def reset_title_cache(self, chat_id: str):
        """Reset title cache for a specific chat (e.g., after branching)."""
        self._last_title_update.pop(chat_id, None)
        self._last_message_count.pop(chat_id, None)
    
    async def should_update_memories(self, force: bool = False) -> bool:
        """Check if memories should be updated."""
        if force:
            return True
        
        if self._pending_memory_update:
            return False
        
        if not self._last_memory_update:
            return True
        
        elapsed = datetime.now() - self._last_memory_update
        return elapsed.total_seconds() >= self.memory_update_interval
    
    async def update_memories(
        self,
        conversation: str,
        model: Optional[str] = None,
        force: bool = False
    ) -> str:
        """Extract and append new memories."""
        if not force and self._pending_memory_update:
            return ""
        
        self._pending_memory_update = True
        
        try:
            # Load existing memories
            existing_memories = ""
            if self.memories_file.exists():
                existing_memories = self.memories_file.read_text()
            
            # Extract new memories
            new_memories = await self.client.extract_memories(
                conversation,
                existing_memories,
                model or "anthropic/claude-3.5-haiku"
            )
            
            # Append to file if we got new content
            if new_memories.strip():
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                with open(self.memories_file, "a") as f:
                    f.write(f"\n\n---\n**Updated: {timestamp}**\n\n{new_memories}\n")
            
            self._last_memory_update = datetime.now()
            
            return new_memories
        
        finally:
            self._pending_memory_update = False
    
    def load_memories(self, max_entries: int = 10) -> str:
        """Load recent memories to inject into context."""
        if not self.memories_file.exists():
            return ""
        
        content = self.memories_file.read_text()
        
        # Split by section markers with lookahead for "Updated:" to avoid splitting on --- in content
        # Look for the pattern: ---\n**Updated:
        import re
        section_pattern = r'\n---\n\*\*Updated:'
        sections = re.split(section_pattern, content)
        
        # Rejoin with the separator for all but the first section
        if len(sections) > 1:
            sections = [sections[0]] + [
                f'\n---\n**Updated:{sec}' for sec in sections[1:]
            ]
        
        recent_sections = sections[-max_entries:] if len(sections) > max_entries else sections
        
        return "".join(recent_sections).strip()

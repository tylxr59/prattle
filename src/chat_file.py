"""Chat file management with UUID-based filenames and frontmatter."""
import uuid
import yaml
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict


@dataclass
class ChatMetadata:
    """Metadata stored in chat file frontmatter."""
    chat_id: str
    title: str
    created: str
    modified: str
    model: str
    folder: str = ""  # Empty string means root, otherwise subfolder name
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMetadata":
        """Create from dictionary."""
        return cls(**data)


class ChatFile:
    """Manages reading and writing chat files with frontmatter and sections."""
    
    COMPACT_MARKER = "# --- COMPACT CONTEXT ---"
    FULL_HISTORY_MARKER = "# --- FULL HISTORY ---"
    
    def __init__(self, base_path: Path):
        """Initialize with base chats directory path."""
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def create_new_chat(
        self,
        title: str = "New Chat",
        model: str = "anthropic/claude-3.5-sonnet",
        folder: str = ""
    ) -> tuple[str, Path]:
        """Create a new chat file with UUID. Returns (chat_id, file_path)."""
        chat_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        
        metadata = ChatMetadata(
            chat_id=chat_id,
            title=title,
            created=now,
            modified=now,
            model=model,
            folder=folder
        )
        
        file_path = self._get_file_path(chat_id, folder)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        content = self._format_chat_file(metadata, "", "")
        file_path.write_text(content)
        
        return chat_id, file_path
    
    def load_chat(self, chat_id: str, folder: str = "") -> Optional[Dict[str, Any]]:
        """Load chat file and return metadata, compact context, and full history."""
        file_path = self._get_file_path(chat_id, folder)
        
        if not file_path.exists():
            # Try to find it in any folder
            file_path = self._find_chat_file(chat_id)
            if not file_path:
                return None
        
        content = file_path.read_text()
        return self._parse_chat_file(content)
    
    def load_compact_context(self, chat_id: str, folder: str = "") -> Optional[str]:
        """Load only the compact context section for API calls."""
        chat_data = self.load_chat(chat_id, folder)
        if chat_data:
            return chat_data["compact_context"]
        return None
    
    def save_chat(
        self,
        chat_id: str,
        metadata: ChatMetadata,
        compact_context: str,
        full_history: str,
    ) -> Path:
        """Save chat file with updated content."""
        metadata.modified = datetime.utcnow().isoformat() + "Z"
        
        file_path = self._get_file_path(chat_id, metadata.folder)
        old_path = self._find_chat_file(chat_id)
        
        # If folder changed, move the file
        if old_path and old_path != file_path:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.rename(file_path)
        
        content = self._format_chat_file(metadata, compact_context, full_history)
        file_path.write_text(content)
        
        return file_path
    
    def update_metadata(self, chat_id: str, **kwargs) -> bool:
        """Update specific metadata fields without rewriting full file."""
        chat_data = self.load_chat(chat_id)
        if not chat_data:
            return False
        
        metadata = chat_data["metadata"]
        for key, value in kwargs.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)
        
        self.save_chat(
            chat_id,
            metadata,
            chat_data["compact_context"],
            chat_data["full_history"]
        )
        return True
    
    def list_chats(self, folder: str = None) -> List[ChatMetadata]:
        """List all chats, optionally filtered by folder. Returns sorted by modified time."""
        chats = []
        
        # Determine which directories to search
        if folder is None:
            # Search all directories recursively
            search_paths = [self.base_path]
        elif folder == "":
            # Search only root directory
            search_paths = [self.base_path]
        else:
            # Search specific folder
            search_paths = [self.base_path / folder]
        
        for search_path in search_paths:
            if not search_path.exists():
                continue
                
            for file_path in search_path.rglob("*.md"):
                try:
                    content = file_path.read_text()
                    data = self._parse_chat_file(content)
                    if data:
                        chats.append(data["metadata"])
                except Exception as e:
                    logging.error(f"Failed to parse chat file {file_path}: {e}")
                    continue
        
        # Sort by modified time (most recent first)
        chats.sort(key=lambda x: x.modified, reverse=True)
        return chats
    
    def move_chat(self, chat_id: str, target_folder: str) -> bool:
        """Move chat to a different folder."""
        chat_data = self.load_chat(chat_id)
        if not chat_data:
            return False
        
        metadata = chat_data["metadata"]
        metadata.folder = target_folder
        
        self.save_chat(
            chat_id,
            metadata,
            chat_data["compact_context"],
            chat_data["full_history"]
        )
        return True
    
    def _get_file_path(self, chat_id: str, folder: str = "") -> Path:
        """Get the file path for a chat ID."""
        if folder:
            return self.base_path / folder / f"{chat_id}.md"
        return self.base_path / f"{chat_id}.md"
    
    def _find_chat_file(self, chat_id: str) -> Optional[Path]:
        """Find a chat file by ID in any folder."""
        for file_path in self.base_path.rglob(f"{chat_id}.md"):
            return file_path
        return None
    
    def _format_chat_file(
        self,
        metadata: ChatMetadata,
        compact_context: str,
        full_history: str
    ) -> str:
        """Format a complete chat file with frontmatter and sections."""
        frontmatter = yaml.dump(metadata.to_dict(), default_flow_style=False)
        
        return f"""---
{frontmatter}---

{self.COMPACT_MARKER}
{compact_context}

{self.FULL_HISTORY_MARKER}
{full_history}
"""
    
    def _parse_chat_file(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse a chat file and extract metadata and sections."""
        # Extract frontmatter
        if not content.startswith("---"):
            return None
        
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
        
        try:
            metadata_dict = yaml.safe_load(parts[1])
            metadata = ChatMetadata.from_dict(metadata_dict)
        except Exception as e:
            logging.error(f"Failed to parse metadata from chat file: {e}")
            return None
        
        body = parts[2]
        
        # Split into compact and full sections
        if self.COMPACT_MARKER in body and self.FULL_HISTORY_MARKER in body:
            sections = body.split(self.FULL_HISTORY_MARKER, 1)
            compact_section = sections[0].replace(self.COMPACT_MARKER, "").strip()
            full_section = sections[1].strip()
        else:
            # Fallback: treat everything as both compact and full
            compact_section = body.strip()
            full_section = body.strip()
        
        return {
            "metadata": metadata,
            "compact_context": compact_section,
            "full_history": full_section
        }

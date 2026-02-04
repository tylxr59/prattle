"""Command handling for chat operations."""
import re
import json
import logging
from pathlib import Path
from typing import Optional, Callable, Awaitable
from datetime import datetime

from .constants import DEFAULT_UTILITY_MODEL, MAX_SEARCH_RESULTS, DEFAULT_TOP_RESULTS, USER_HEADER


class CommandHandler:
    """Handles chat commands like /switch, /compact, /branch, etc."""
    
    def __init__(self):
        """Initialize command handler."""
        self.commands: dict[str, Callable] = {
            "help": self.cmd_help,
            "switch": self.cmd_switch,
            "compact": self.cmd_compact,
            "branch": self.cmd_branch,
            "move": self.cmd_move,
            "search": self.cmd_search,
            "models": self.cmd_models,
            "clear": self.cmd_clear,
            "parse": self.cmd_parse,
            "settings": self.cmd_settings,
            "delete": self.cmd_delete,
        }
    
    def is_command(self, text: str) -> bool:
        """Check if text is a command."""
        return text.strip().startswith("/")
    
    def parse_command(self, text: str) -> tuple[str, list[str]]:
        """Parse command and arguments. Returns (command_name, args)."""
        text = text.strip()
        if not text.startswith("/"):
            return "", []
        
        parts = text[1:].split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1].split() if len(parts) > 1 else []
        
        return command, args
    
    async def execute(
        self,
        text: str,
        context: dict
    ) -> tuple[bool, Optional[str]]:
        """
        Execute a command.
        
        Returns (success, message).
        Context dict should contain: app, chat_file, openrouter, memory_manager, etc.
        """
        command, args = self.parse_command(text)
        
        if command not in self.commands:
            return False, f"Unknown command: /{command}. Type /help for available commands."
        
        handler = self.commands[command]
        return await handler(args, context)
    
    async def cmd_help(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Show help information."""
        help_text = """
**Available Commands:**

- /help - Show this help message
- /settings - Open settings editor
- /switch <model> - Switch to a different model
- /models - Browse and select from available models
- /compact - Summarize chat history to reduce context size
- /branch [message_num] - Create a new chat branching from a specific point
- /move <folder> - Move current chat to a folder
- /search <query> - Search across all chats
- /parse - Force update title and memories
- /clear - Clear current chat messages (keeps file)
- /delete - Delete the current chat permanently (shows confirmation dialog)

**Keybindings:**

- Ctrl+N: New chat
- Ctrl+F: Search chats
- Ctrl+B: Toggle sidebar
- Ctrl+Enter: Send message
- Ctrl+M: Browse models
- Ctrl+H: Show help
- Ctrl+,: Settings
- Ctrl+Q: Quit
"""
        return True, help_text
    
    async def cmd_switch(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Switch to a different model."""
        if not args:
            current_model = context.get("current_model", "unknown")
            return False, f"Current model: {current_model}. Usage: /switch <model_id>"
        
        model_id = " ".join(args)
        
        # Validate model exists
        openrouter = context.get("openrouter")
        if openrouter:
            model_info = await openrouter.get_model_info(model_id)
            if not model_info:
                return False, f"Model not found: {model_id}. Use /models to browse available models."
        
        # Update context
        context["current_model"] = model_id
        
        # Update chat metadata
        chat_file = context.get("chat_file")
        chat_id = context.get("current_chat_id")
        if chat_file and chat_id:
            chat_file.update_metadata(chat_id, model=model_id)
        
        return True, f"Switched to model: {model_id}"
    
    async def cmd_compact(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Compact chat history by summarizing."""
        chat_file = context.get("chat_file")
        chat_id = context.get("current_chat_id")
        openrouter = context.get("openrouter")
        
        if not all([chat_file, chat_id, openrouter]):
            return False, "Cannot compact: missing required context."
        
        # Type narrowing - all three are guaranteed non-None after the check above
        assert chat_file is not None
        assert chat_id is not None
        assert openrouter is not None
        
        # Load current chat
        chat_data = chat_file.load_chat(chat_id)
        if not chat_data:
            return False, "Failed to load current chat."
        
        full_history = chat_data["full_history"]
        
        # Generate summary
        messages = [
            {
                "role": "system",
                "content": "Summarize this conversation concisely, preserving key information, "
                          "decisions, and context. Format as a narrative summary."
            },
            {
                "role": "user",
                "content": f"Conversation to summarize:\n\n{full_history}"
            }
        ]
        
        summary = ""
        current_model = context.get("current_model", DEFAULT_UTILITY_MODEL)
        
        async for content, _ in openrouter.chat_completion(messages, current_model, stream=False):
            summary += content
        
        # Append old compact context to full history, then set new summary as compact
        metadata = chat_data["metadata"]
        old_compact = chat_data["compact_context"]
        
        new_full_history = f"{full_history}\n\n<!-- Previous compact context -->\n{old_compact}\n"
        new_compact_context = f"**Summary (generated {datetime.now().strftime('%Y-%m-%d %H:%M')})**\n\n{summary}"
        
        # Save
        chat_file.save_chat(chat_id, metadata, new_compact_context, new_full_history)
        
        return True, "Chat history compacted successfully."
    
    async def cmd_branch(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Branch conversation from a specific point."""
        chat_file = context.get("chat_file")
        chat_id = context.get("current_chat_id")
        
        if not all([chat_file, chat_id]):
            return False, "Cannot branch: missing required context."
        
        # Type narrowing - both are guaranteed non-None after the check above
        assert chat_file is not None
        assert chat_id is not None
        
        # Load current chat
        chat_data = chat_file.load_chat(chat_id)
        if not chat_data:
            return False, "Failed to load current chat."
        
        # For now, branch from current point (can enhance to support message numbers)
        metadata = chat_data["metadata"]
        
        # Create new chat with same content
        new_chat_id, _ = chat_file.create_new_chat(
            title=f"{metadata.title} (branch)",
            model=metadata.model,
            folder=metadata.folder
        )
        
        # Copy content
        chat_file.save_chat(
            new_chat_id,
            chat_data["metadata"],
            chat_data["compact_context"],
            chat_data["full_history"]
        )
        
        # Switch to new chat
        context["current_chat_id"] = new_chat_id
        
        # Reset title cache for new chat
        memory_manager = context.get("memory_manager")
        if memory_manager:
            memory_manager.reset_title_cache(new_chat_id)
        
        return True, f"Created branch: {new_chat_id}"
    
    async def cmd_move(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Move current chat to a folder."""
        if not args:
            return False, "Usage: /move <folder_name>"
        
        folder = args[0]
        chat_file = context.get("chat_file")
        chat_id = context.get("current_chat_id")
        
        if not chat_file or not chat_id:
            return False, "Cannot move: missing required context."
        
        success = chat_file.move_chat(chat_id, folder)
        
        if success:
            return True, f"Moved chat to folder: {folder}"
        else:
            return False, "Failed to move chat."
    
    async def cmd_search(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Search across all chats using grep."""
        if not args:
            return False, "Usage: /search <query>"
        
        query = " ".join(args)
        chat_file = context.get("chat_file")
        
        if not chat_file:
            return False, "Cannot search: missing chat file handler."
        
        # Simple grep through all markdown files
        results = []
        chats_path = chat_file.base_path
        
        for file_path in chats_path.rglob("*.md"):
            try:
                content = file_path.read_text()
                
                # Search in content (case-insensitive)
                if query.lower() in content.lower():
                    # Try to extract title from metadata
                    title = "Unknown"
                    lines = content.split('\n', 1)
                    first_line = lines[0].strip()
                    
                    # Try JSON format first (new format)
                    if first_line.startswith('{'):
                        try:
                            metadata = json.loads(first_line)
                            title = metadata.get('title', 'Unknown')
                        except json.JSONDecodeError:
                            pass
                    # Fall back to YAML format (old format)
                    elif content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 2 and "title:" in parts[1]:
                            for line in parts[1].split("\n"):
                                if line.strip().startswith("title:"):
                                    title = line.split(":", 1)[1].strip().strip('"').strip("'")
                                    break
                    
                    # Find matching lines
                    lines = content.split("\n")
                    matching_lines = [
                        (i+1, line) for i, line in enumerate(lines)
                        if query.lower() in line.lower()
                    ][:DEFAULT_TOP_RESULTS]  # First 3 matches per file
                    
                    results.append({
                        "file": file_path.name,
                        "title": title,
                        "matches": matching_lines
                    })
            
            except Exception as e:
                logging.warning(f"Error searching file {file_path}: {e}")
                continue
        
        if not results:
            return True, f"No results found for: {query}"
        
        # Format results
        output = f"**Found {len(results)} chat(s) matching '{query}':**\n\n"
        for result in results[:MAX_SEARCH_RESULTS]:  # Limit to 10 results
            output += f"**{result['title']}** ({result['file']})\n"
            for line_num, line in result["matches"]:
                output += f"  Line {line_num}: {line.strip()[:100]}\n"
            output += "\n"
        
        return True, output
    
    async def cmd_models(self, args: list[str], context: dict) -> tuple[bool, str]:
        """List available models (trigger UI model selector)."""
        # This command will be handled specially by the app to show a model selector UI
        return True, "SHOW_MODEL_SELECTOR"
    
    async def cmd_clear(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Clear current chat messages."""
        chat_file = context.get("chat_file")
        chat_id = context.get("current_chat_id")
        
        if not all([chat_file, chat_id]):
            return False, "Cannot clear: missing required context."
        
        if not chat_file:
            return False, "Chat file handler not available."
        
        chat_data = chat_file.load_chat(chat_id)
        if not chat_data:
            return False, "Failed to load current chat."
        
        # Clear history but keep metadata
        metadata = chat_data["metadata"]
        chat_file.save_chat(chat_id, metadata, "", "")
        
        return True, "Chat cleared."
    
    async def cmd_parse(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Force update title and memories."""
        memory_manager = context.get("memory_manager")
        chat_file = context.get("chat_file")
        chat_id = context.get("current_chat_id")
        
        if not all([memory_manager, chat_file, chat_id]):
            return False, "Cannot parse: missing required context."
        
        # Load chat
        chat_data = chat_file.load_chat(chat_id) if chat_file else None
        if not chat_data:
            return False, "Failed to load current chat."
        
        if not memory_manager:
            return False, "Memory manager not available."
        
        full_history = chat_data["full_history"]
        
        # Count messages using the new format only
        message_count = full_history.count(USER_HEADER)
        
        # Update title
        title = await memory_manager.update_title(
            chat_id,
            full_history,
            message_count,
            force=True
        )
        
        if title and chat_file:
            chat_file.update_metadata(chat_id, title=title)
        
        # Update memories
        await memory_manager.update_memories(full_history, force=True)
        
        return True, "Updated title and memories."
    
    async def cmd_settings(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Open settings editor (trigger UI settings screen)."""
        # This command will be handled specially by the app to show settings UI
        return True, "SHOW_SETTINGS_UI"
    
    async def cmd_delete(self, args: list[str], context: dict) -> tuple[bool, str]:
        """Delete the current chat permanently."""
        chat_file = context.get("chat_file")
        chat_id = context.get("current_chat_id")
        
        if not chat_file or not chat_id:
            return False, "Cannot delete: missing required context."
        
        # Find and delete the chat file
        file_path = chat_file._find_chat_file(chat_id)
        if not file_path or not file_path.exists():
            logging.error(f"Chat file not found for deletion: {chat_id}")
            return False, "Chat file not found."
        
        # Delete the file
        try:
            file_path.unlink()
            logging.info(f"Deleted chat: {chat_id}")
        except Exception as e:
            logging.error(f"Failed to delete chat {chat_id}: {e}")
            return False, f"Failed to delete chat: {e}"
        
        # Signal success
        return True, "DELETE_CHAT"

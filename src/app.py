"""Main Textual TUI application."""
import os
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Input, TextArea, ListView, ListItem, Label, OptionList, Markdown
from textual.widgets.option_list import Option
from textual.reactive import reactive
from textual import events, on, work
from textual.worker import Worker
from textual.message import Message
from textual.binding import Binding
from rich.text import Text

from dotenv import load_dotenv

from .chat_file import ChatFile, ChatMetadata
from .openrouter import OpenRouterClient, TokenUsage
from .memory import MemoryManager
from .commands import CommandHandler
from .settings_ui import SettingsScreen
from .constants import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_TITLE_UPDATE_INTERVAL,
    DEFAULT_MEMORY_UPDATE_INTERVAL,
    MAX_MEMORY_ENTRIES,
    USER_HEADER,
    ASSISTANT_HEADER
)
from .utils import parse_message_history, format_token_usage


class ChatInput(TextArea):
    """Custom TextArea for chat input that submits on Enter and adds newline on Shift+Enter."""
    
    async def _on_key(self, event: events.Key) -> None:
        """Handle key events."""
        # Shift+Enter: insert newline manually
        if event.key == "shift+enter":
            event.prevent_default()
            self.insert("\n")
            return
        
        # Plain Enter: submit the message
        if event.key == "enter":
            event.prevent_default()
            self.post_message(self.Submitted(self))
            return
        
        # For all other keys, let TextArea handle them normally
        await super()._on_key(event)
    
    class Submitted(Message):
        """Message sent when input is submitted."""
        
        def __init__(self, text_area: "ChatInput") -> None:
            super().__init__()
            self.text_area = text_area
            self.value = text_area.text


class ChatMessage(Container):
    """A single chat message widget."""
    
    def __init__(self, role: str, content: str, timestamp: Optional[str] = None, user_name: str = "You", assistant_name: str = "Assistant"):
        """Initialize chat message."""
        self.role = role
        self.timestamp = timestamp or datetime.utcnow().strftime("%H:%M:%S")
        self.content_text = content
        self.user_name = user_name
        self.assistant_name = assistant_name
        super().__init__(classes=role)  # Add role as CSS class
    
    def compose(self) -> ComposeResult:
        """Compose the message."""
        prefix = f"## {self.user_name}" if self.role == "user" else f"## {self.assistant_name}"
        timestamp_str = f" `[{self.timestamp}]`" if self.timestamp else ""
        
        # Use Textual's Markdown widget directly for proper rendering
        markdown_content = f"{prefix}{timestamp_str}\n\n{self.content_text}"
        yield Markdown(markdown_content, id=f"msg-content-{id(self)}")
    
    def update_content(self, content: str):
        """Update message content (for streaming)."""
        self.content_text = content
        # Update the Markdown widget's content
        try:
            content_widget = self.query_one(f"#msg-content-{id(self)}", Markdown)
            prefix = f"## {self.user_name}" if self.role == "user" else f"## {self.assistant_name}"
            timestamp_str = f" `[{self.timestamp}]`" if self.timestamp else ""
            markdown_content = f"{prefix}{timestamp_str}\n\n{self.content_text}"
            content_widget.update(markdown_content)
        except Exception:
            # Widget may not exist yet during initialization
            pass


class ChatSidebar(Container):
    """Sidebar showing list of chats."""
    
    def __init__(self):
        """Initialize sidebar."""
        super().__init__(id="sidebar")
        self.chat_items: dict[str, ListItem] = {}
    
    def compose(self) -> ComposeResult:
        """Compose the sidebar."""
        yield Static("💬 Chats", id="sidebar-title")
        yield ListView(id="chat-list")


class ChatView(ScrollableContainer):
    """Main chat messages view."""
    
    def __init__(self, user_name: str = "You", assistant_name: str = "Assistant"):
        """Initialize chat view."""
        super().__init__(id="chat-view")
        self.messages: list[ChatMessage] = []
        self.user_name = user_name
        self.assistant_name = assistant_name
        self.welcome_message: Optional[ChatMessage] = None
    
    def add_message(self, role: str, content: str, timestamp: Optional[str] = None) -> ChatMessage:
        """Add a message to the chat view."""
        # If this is a user message and we have a welcome message, remove it
        if role == "user" and self.welcome_message:
            self.welcome_message.remove()
            if self.welcome_message in self.messages:
                self.messages.remove(self.welcome_message)
            self.welcome_message = None
        
        msg = ChatMessage(role, content, timestamp, self.user_name, self.assistant_name)
        self.messages.append(msg)
        self.mount(msg)
        self.scroll_end(animate=False)
        return msg
    
    def update_last_message(self, content: str):
        """Update the content of the last message (for streaming)."""
        if self.messages:
            self.messages[-1].update_content(content)
            self.scroll_end(animate=False)
    
    def add_info_message(self, content: str):
        """Add a small info message (for token/cost info)."""
        info = Static(f"[dim]{content}[/dim]")
        self.mount(info)
        self.scroll_end(animate=False)
    
    def clear_messages(self):
        """Clear all messages and info widgets."""
        # Remove all children (messages and info widgets)
        for child in list(self.children):
            child.remove()
        self.messages.clear()
        self.welcome_message = None
    
    def add_welcome_message(self, content: str) -> ChatMessage:
        """Add a welcome message that will be removed on first user message."""
        msg = self.add_message("system", content)
        self.welcome_message = msg
        return msg


class StatusBar(Static):
    """Status bar showing model, tokens, and cost."""
    
    model: reactive[str] = reactive("No model")
    tokens: reactive[int] = reactive(0)
    cost: reactive[float] = reactive(0.0)
    
    def render(self) -> Text:
        """Render the status bar."""
        return Text.from_markup(
            f"[bold cyan]{self.model}[/] | "
            f"[yellow]{self.tokens}[/] tokens | "
            f"[green]${self.cost:.4f}[/]"
        )
    
    def update_stats(self, model: str, usage: Optional[TokenUsage] = None):
        """Update statistics."""
        self.model = model
        if usage:
            self.tokens = usage.total_tokens
            self.cost = usage.total_cost


class PrattleApp(App):
    """Main Prattle TUI application."""
    
    # Set theme from settings (will be updated in __init__)
    
    CSS = """
    #sidebar {
        width: 30;
        border-right: thick $accent;
        height: 100%;
        background: $surface;
    }
    
    #sidebar-title {
        background: $accent;
        color: $text;
        padding: 1 2;
        text-align: left;
        text-style: bold;
        dock: top;
    }
    
    #chat-list {
        width: 100%;
        height: 1fr;
        background: $surface;
        padding: 0;
    }
    
    #chat-list > ListItem {
        background: $surface;
        padding: 1 2;
        height: auto;
    }
    
    #chat-list > ListItem:hover {
        background: $boost;
    }
    
    #chat-list > ListItem.-highlight {
        background: $accent;
    }
    
    #chat-list Label {
        width: 100%;
        height: auto;
        content-align: left top;
    }
    
    .chat-item-inactive {
        color: $text-muted;
    }
    
    .chat-item-active {
        color: $text;
    }
    
    #chat-container {
        width: 1fr;
        height: 100%;
    }
    
    #chat-view {
        height: 1fr;
        padding: 0 1;
    }
    
    #input-container {
        height: auto;
        padding: 1;
        border-top: solid $accent;
    }
    
    #chat-input {
        height: auto;
        min-height: 3;
        max-height: 10;
    }
    
    #status-bar {
        dock: bottom;
        height: 1;
        background: $panel;
        padding: 0 1;
    }
    
    ChatMessage {
        width: 100%;
        height: auto;
        margin: 1 0;
        padding: 0;
    }
    
    ChatMessage.user {
        align: right top;
    }
    
    ChatMessage.assistant {
        align: left top;
    }
    
    ChatMessage.system {
        align: center top;
    }
    
    ChatMessage > Markdown {
        width: auto;
        max-width: 80%;
        padding: 0 2 1 2;
        margin: 0;
    }
    
    ChatMessage.user > Markdown {
        background: $panel;
        border: solid $accent;
    }
    
    ChatMessage.assistant > Markdown {
        background: $panel;
        border: solid $accent-darken-1;
    }
    
    ChatMessage.system > Markdown {
        background: $surface;
        border: solid $warning;
        text-align: center;
    }
    
    .title-notification {
        width: 100%;
        text-align: center;
        color: $text-muted;
        padding: 0 1;
        margin: 1 0;
    }
    """
    
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+n", "new_chat", "New Chat"),
        ("ctrl+d", "delete_chat", "Delete Chat"),
        ("ctrl+f", "search_chats", "Search"),
        ("ctrl+b", "toggle_sidebar", "Toggle Sidebar"),
        ("ctrl+h", "show_help", "Help"),
        ("ctrl+m", "show_models", "Models"),
        ("ctrl+comma", "show_settings", "Settings"),
        ("tab", "toggle_focus", "Switch Focus"),
    ]
    
    def __init__(self):
        """Initialize the app."""
        super().__init__()
        
        # Load environment and settings
        load_dotenv()
        self.base_path = Path.cwd()
        self.settings_file = self.base_path / "settings.json"
        self.settings = self._load_or_create_settings()
        
        # Initialize components
        self.chat_file = ChatFile(self.base_path / "chats")
        
        # Get API key from environment variable only (not settings.json for security)
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logging.warning("No OPENROUTER_API_KEY found in environment. Set it in .env file.")
            # Allow app to start - user will get error when trying to send messages
            api_key = "MISSING_API_KEY_SET_IN_ENV"
        
        self.openrouter = OpenRouterClient(api_key)
        
        self.memory_manager = MemoryManager(
            self.openrouter,
            self.base_path / "context" / "memories.md",
            title_update_interval=self.settings.get("title_update_interval", DEFAULT_TITLE_UPDATE_INTERVAL),
            memory_update_interval=self.settings.get("memory_update_interval", DEFAULT_MEMORY_UPDATE_INTERVAL),
        )
        
        self.command_handler = CommandHandler()
        
        # Current state
        self.current_chat_id: Optional[str] = None
        self.current_model: str = self.settings.get("default_model", DEFAULT_CHAT_MODEL)
        self.system_prompt: str = self._load_system_prompt()
        
        # Auto-update workers
        self._title_update_worker: Optional[Worker] = None
        
        # Apply theme from settings
        self.theme = self.settings.get("ui", {}).get("theme", "textual-dark")
    
    def _load_or_create_settings(self) -> dict:
        """Load settings from settings.json or create default."""
        if self.settings_file.exists():
            try:
                settings = json.loads(self.settings_file.read_text())
                # Ensure all required keys exist (in case settings was created with older version)
                if "ui" not in settings:
                    settings["ui"] = {
                        "show_timestamps": True,
                        "syntax_theme": "monokai",
                        "sidebar_width": 30,
                        "theme": "textual-dark"
                    }
                # Ensure theme field exists for older settings files
                if "theme" not in settings.get("ui", {}):
                    settings["ui"]["theme"] = "textual-dark"
                return settings
            except json.JSONDecodeError:
                # If file is corrupted, create default
                pass
        
        # Create default settings
        default_settings = {
            "default_model": DEFAULT_CHAT_MODEL,
            "title_update_interval": DEFAULT_TITLE_UPDATE_INTERVAL,
            "memory_update_interval": DEFAULT_MEMORY_UPDATE_INTERVAL,
            "max_memory_entries_in_context": MAX_MEMORY_ENTRIES,
            "keybindings": {
                "quit": "ctrl+q",
                "new_chat": "ctrl+n",
                "search_chats": "ctrl+f",
                "toggle_sidebar": "ctrl+b",
                "send_message": "ctrl+enter",
                "clear_input": "ctrl+u",
                "show_help": "ctrl+h",
                "show_models": "ctrl+m",
                "show_settings": "ctrl+,"
            },
            "ui": {
                "show_timestamps": True,
                "syntax_theme": "monokai",
                "sidebar_width": 30,
                "theme": "textual-dark"
            }
        }
        
        # Save default settings
        self.settings_file.write_text(json.dumps(default_settings, indent=2))
        return default_settings
    
    def _load_system_prompt(self) -> str:
        """Load system prompt from context/prompt.md."""
        prompt_path = self.base_path / "context" / "prompt.md"
        if prompt_path.exists():
            return prompt_path.read_text()
        return "You are a helpful AI assistant."
    
    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        with Horizontal():
            yield ChatSidebar()
            
            with Container(id="chat-container"):
                user_name = self.settings.get("user_name", "You")
                assistant_name = self.settings.get("assistant_name", "Assistant")
                yield ChatView(user_name=user_name, assistant_name=assistant_name)
                
                with Container(id="input-container"):
                    yield ChatInput(id="chat-input")
        
        yield StatusBar(id="status-bar")
        yield Footer()
    
    async def on_mount(self) -> None:
        """Initialize app after mounting."""
        # Load chat list
        await self._refresh_chat_list()
        
        # Load most recent chat if available
        chats = self.chat_file.list_chats()
        if chats:
            await self._load_chat(chats[0].chat_id)
        else:
            # No chats yet - show welcome message
            chat_view = self.query_one(ChatView)
            chat_view.add_message("system", "No chats yet. Press **Ctrl+N** to create a new chat.")
        
        # Add tip about multi-line input
        chat_view = self.query_one(ChatView)
        if not chats or len(chats) == 0:
            chat_view.add_info_message("💡 Tip: Press Enter to send, Shift+Enter for new line")
        
        # Note: Title updates are triggered after each message is sent
        # No background polling needed - see _send_message() -> _check_title_update()
    
    async def _refresh_chat_list(self):
        """Refresh the sidebar chat list."""
        chat_list = self.query_one("#chat-list", ListView)
        
        # Remove all children to fully clear the list
        await chat_list.remove_children()
        
        chats = self.chat_file.list_chats()
        
        if not chats:
            # Show "No chats yet" message when empty
            item = ListItem(Label("[dim italic]No chats yet[/dim italic]"))
            await chat_list.mount(item)
        else:
            for chat in chats:
                # Check if this is the active chat
                is_active = chat.chat_id == self.current_chat_id
                
                # Build display text without truncation - let it wrap
                if chat.folder:
                    # For folders: "📁 folder/title"
                    display = f"📁 {chat.folder}/{chat.title}"
                else:
                    # For regular: "• title" or "> title"
                    bullet = "> " if is_active else "• "
                    title = chat.title
                    
                    # Apply bold formatting to active chat title
                    if is_active:
                        title = f"[bold]{title}[/bold]"
                    
                    display = f"{bullet}{title}"
                
                # Create label that will wrap naturally
                label = Label(display)
                # Add class based on active state
                if is_active:
                    label.add_class("chat-item-active")
                else:
                    label.add_class("chat-item-inactive")
                
                item = ListItem(label, id=f"chat-{chat.chat_id}")
                await chat_list.mount(item)
    
    async def _create_new_chat(self):
        """Create a new chat."""
        # Use the default model from settings for new chats
        default_model = self.settings.get("default_model", DEFAULT_CHAT_MODEL)
        
        chat_id, _ = self.chat_file.create_new_chat(
            title="New Chat",
            model=default_model
        )
        
        logging.info(f"Created new chat: {chat_id} with model {default_model}")
        
        self.current_chat_id = chat_id
        self.current_model = default_model
        
        # Clear chat view
        chat_view = self.query_one(ChatView)
        chat_view.clear_messages()
        
        # Show model info in the new chat (will disappear on first message)
        chat_view.add_welcome_message(f"🤖 Using model: **{default_model}**\n\nType your message below to start chatting.")
        
        # Update status
        status_bar = self.query_one(StatusBar)
        status_bar.update_stats(self.current_model)
        
        # Refresh sidebar
        await self._refresh_chat_list()
    
    async def _load_chat(self, chat_id: str):
        """Load an existing chat."""
        chat_data = self.chat_file.load_chat(chat_id)
        if not chat_data:
            logging.error(f"Failed to load chat: {chat_id}")
            return
        
        self.current_chat_id = chat_id
        metadata = chat_data["metadata"]
        self.current_model = metadata.model
        
        logging.info(f"Loaded chat: {chat_id} ({metadata.title}) with model {metadata.model}")
        
        # Clear and populate chat view
        chat_view = self.query_one(ChatView)
        chat_view.clear_messages()
        
        # Parse and display messages from full history
        full_history = chat_data["full_history"]
        
        # Parse messages using utility function
        for role, content, token_info in parse_message_history(full_history):
            chat_view.add_message(role, content)
            # Add token/cost info if it exists (only for assistant messages)
            if token_info and role == "assistant":
                chat_view.add_info_message(token_info)
        
        # Update status
        status_bar = self.query_one(StatusBar)
        status_bar.update_stats(self.current_model)
        
        # Refresh sidebar to update active chat indicator
        await self._refresh_chat_list()
    
    @on(ChatInput.Submitted)
    async def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        """Handle message submission from chat input."""
        message = event.value.strip()
        if not message:
            return
        
        # Clear input
        event.text_area.clear()
        
        # Check if it's a command
        if self.command_handler.is_command(message):
            await self._handle_command(message)
            return
        
        # Add user message to view
        chat_view = self.query_one(ChatView)
        chat_view.add_message("user", message)
        
        # Send to API
        await self._send_message(message)
    
    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle chat selection from sidebar."""
        if event.item.id and event.item.id.startswith("chat-"):
            # Strip the 'chat-' prefix to get the actual chat ID
            chat_id = event.item.id[5:]  # Remove 'chat-' prefix
            await self._load_chat(chat_id)
    
    async def _handle_command(self, command_text: str):
        """Handle a command."""
        context = {
            "app": self,
            "chat_file": self.chat_file,
            "openrouter": self.openrouter,
            "memory_manager": self.memory_manager,
            "current_chat_id": self.current_chat_id,
            "current_model": self.current_model,
        }
        
        success, message = await self.command_handler.execute(command_text, context)
        
        # Update current model if changed
        self.current_model = context.get("current_model", self.current_model)
        
        # Show response
        if message == "SHOW_MODEL_SELECTOR":
            await self._show_model_selector()
        elif message == "SHOW_SETTINGS_UI":
            self.action_show_settings()
        elif message == "DELETE_CHAT":
            # Chat was deleted, clear view and show welcome if no chats remain
            chat_view = self.query_one(ChatView)
            chat_view.clear_messages()
            self.current_chat_id = None
            
            await self._refresh_chat_list()
            
            # Check if there are any remaining chats
            chats = self.chat_file.list_chats()
            if chats:
                # Load the most recent chat
                await self._load_chat(chats[0].chat_id)
                # Focus the sidebar list so user can navigate
                try:
                    chat_list = self.query_one("#chat-list", ListView)
                    chat_list.focus()
                except Exception:
                    pass
            else:
                # No chats left - show welcome message
                chat_view.add_message("system", "No chats yet. Press **Ctrl+N** to create a new chat.")
        elif message:
            chat_view = self.query_one(ChatView)
            role = "assistant" if success else "system"
            chat_view.add_message(role, message)
    
    def _build_api_messages(self, chat_data: dict, user_message: str) -> list:
        """Build message list for API call from context and history.
        
        Args:
            chat_data: Loaded chat data containing history and context
            user_message: Current user message to append
            
        Returns:
            List of message dicts for API
        """
        messages = []
        
        # System prompt
        messages.append({"role": "system", "content": self.system_prompt})
        
        # Memories
        memories = self.memory_manager.load_memories(
            self.settings.get("max_memory_entries_in_context", MAX_MEMORY_ENTRIES)
        )
        if memories:
            messages.append({"role": "system", "content": f"# Relevant Memories\\n\\n{memories}"})
        
        # Compact context (previous conversation summary) - only if exists
        compact_context = chat_data["compact_context"]
        if compact_context:
            messages.append({"role": "system", "content": f"# Previous Context\\n\\n{compact_context}"})
        
        # Add conversation history from this chat
        full_history = chat_data["full_history"]
        if full_history.strip():
            # Parse history using utility function (ignore token info)
            for role, content, _token_info in parse_message_history(full_history):
                messages.append({"role": role, "content": content})
        
        # Current user message
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    async def _stream_response(self, messages: list, chat_view: ChatView) -> tuple[str, Optional[TokenUsage]]:
        """Stream API response and update chat view in real-time.
        
        Args:
            messages: Message list for API
            chat_view: Chat view widget to update
            
        Returns:
            Tuple of (complete_response, usage_info)
        """
        response_content = ""
        usage = None
        
        # Add "Thinking..." placeholder while waiting for first token
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        chat_view.add_message("assistant", "*Thinking...*", timestamp)
        
        try:
            first_chunk = True
            async for content, msg_usage in self.openrouter.chat_completion(
                messages,
                self.current_model,
                stream=True
            ):
                if content:
                    response_content += content
                    # On first chunk, replace "Thinking..." with actual content
                    if first_chunk:
                        chat_view.update_last_message(response_content + "█")
                        first_chunk = False
                    else:
                        # Update the message in real-time with streaming content
                        chat_view.update_last_message(response_content + "█")
                
                if msg_usage:
                    usage = msg_usage
            
            # Remove cursor and show final content
            chat_view.update_last_message(response_content)
            
        except Exception as e:
            logging.error(f"Error streaming response: {e}", exc_info=True)
            chat_view.update_last_message(f"[Error: {str(e)}]")
            raise
        
        return response_content, usage

    async def _send_message(self, user_message: str):
        """
        Send message to API and stream response.
        
        Builds context from system prompt, memories, compact context, and history,
        then streams the response and saves to chat file.
        
        Args:
            user_message: The user's message to send
        """
        if not self.current_chat_id:
            logging.warning("Attempted to send message with no active chat")
            return
        
        # Load chat history
        chat_data = self.chat_file.load_chat(self.current_chat_id)
        if not chat_data:
            logging.error(f"Failed to load chat data for {self.current_chat_id}")
            return
        
        # Build messages for API
        messages = self._build_api_messages(chat_data, user_message)
        
        # Stream response
        chat_view = self.query_one(ChatView)
        
        try:
            response_content, usage = await self._stream_response(messages, chat_view)
            
            # Show token usage and cost info
            if usage:
                info_text = format_token_usage(
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_cost,
                    self.current_model
                )
                chat_view.add_info_message(info_text)
                
                # Update status bar
                status_bar = self.query_one(StatusBar)
                status_bar.update_stats(self.current_model, usage)
            
            # Save to chat file (append to full history)
            await self._save_message_to_file(user_message, response_content, usage)
            
            # Trigger title update check
            await self._check_title_update()
        
        except Exception as e:
            logging.error(f"Error in _send_message: {e}", exc_info=True)
    
    async def _save_message_to_file(self, user_msg: str, assistant_msg: str, usage: Optional[TokenUsage] = None):
        """Save messages to chat file."""
        if not self.current_chat_id:
            return
        
        chat_data = self.chat_file.load_chat(self.current_chat_id)
        if not chat_data:
            return
        
        metadata = chat_data["metadata"]
        compact_context = chat_data["compact_context"]
        full_history = chat_data["full_history"]
        
        # Import escape function
        from .utils import escape_message_headers
        
        # Escape any message headers in user/assistant content to prevent parsing issues
        user_msg_escaped = escape_message_headers(user_msg)
        assistant_msg_escaped = escape_message_headers(assistant_msg)
        
        # Append to full history
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        full_history += f"\n\n## User `[{timestamp}]`\n\n{user_msg_escaped}\n\n## Assistant `[{timestamp}]`\n\n{assistant_msg_escaped}\n"
        
        # Add token/cost info if available
        if usage:
            full_history += f"\n*{format_token_usage(usage.prompt_tokens, usage.completion_tokens, usage.total_cost, self.current_model)}*\n"
        
        # Don't auto-populate compact context - only user can do this with /compact command
        # compact_context remains empty until explicitly compacted
        
        self.chat_file.save_chat(
            self.current_chat_id,
            metadata,
            compact_context,
            full_history
        )
    
    async def _check_title_update(self):
        """Check and update title if needed."""
        if not self.current_chat_id:
            return
        
        chat_data = self.chat_file.load_chat(self.current_chat_id)
        if not chat_data:
            return
        
        full_history = chat_data["full_history"]
        # Count messages using the new format only
        message_count = full_history.count(USER_HEADER)
        
        should_update = await self.memory_manager.should_update_title(
            self.current_chat_id,
            message_count
        )
        
        if should_update and full_history.strip():
            title = await self.memory_manager.update_title(
                self.current_chat_id,
                full_history,
                message_count,
                self.current_model
            )
            
            if title:
                self.chat_file.update_metadata(self.current_chat_id, title=title)
                await self._refresh_chat_list()
                
                # Show notification in chat as a simple info line
                chat_view = self.query_one(ChatView)
                info = Static(f"[dim italic]Title updated to: {title}[/dim italic]", classes="title-notification")
                chat_view.mount(info)
                chat_view.scroll_end(animate=False)
    
    async def _show_model_selector(self):
        """Show model selector (placeholder - would show a modal in full implementation)."""
        models = await self.openrouter.list_models()
        
        model_list = "\n".join([f"- {m.id}: {m.name}" for m in models[:20]])
        
        chat_view = self.query_one(ChatView)
        chat_view.add_message("system", f"**Available Models (top 20):**\n\n{model_list}\n\nUse `/switch <model_id>` to switch.")
    
    def action_new_chat(self):
        """Create a new chat."""
        asyncio.create_task(self._create_new_chat())
    
    def action_delete_chat(self):
        """Delete the current chat."""
        if self.current_chat_id:
            asyncio.create_task(self._handle_command("/delete"))
    
    def action_search_chats(self):
        """Search chats (placeholder)."""
        pass
    
    def action_toggle_sidebar(self):
        """Toggle sidebar visibility."""
        sidebar = self.query_one(ChatSidebar)
        sidebar.display = not sidebar.display
    
    def action_toggle_focus(self):
        """Toggle focus between chat input and sidebar."""
        try:
            # Get both the sidebar list and input
            chat_list = self.query_one("#chat-list", ListView)
            chat_input = self.query_one("#chat-input", ChatInput)
            
            # Check which one currently has focus
            if chat_input.has_focus:
                # Switch to sidebar
                chat_list.focus()
            else:
                # Switch to input
                chat_input.focus()
        except Exception:
            # If we can't determine focus, default to input
            try:
                chat_input = self.query_one("#chat-input", ChatInput)
                chat_input.focus()
            except Exception:
                pass
    
    def action_show_help(self):
        """Show help."""
        asyncio.create_task(self._handle_command("/help"))
    
    def action_show_models(self):
        """Show models."""
        asyncio.create_task(self._handle_command("/models"))
    
    def action_show_settings(self):
        """Show settings screen."""
        def check_settings(new_settings: Optional[dict]) -> None:
            """Callback when settings screen closes."""
            if new_settings:
                # Reload settings
                self.settings = new_settings
                
                # Update API key if changed
                api_key = new_settings.get("openrouter_api_key")
                if api_key and api_key != "dummy_key_to_be_set_in_settings":
                    self.openrouter.api_key = api_key
                
                # Update model if changed
                self.current_model = new_settings.get("default_model", self.current_model)
                
                # Update user/assistant names if changed
                chat_view = self.query_one(ChatView)
                chat_view.user_name = new_settings.get("user_name", "You")
                chat_view.assistant_name = new_settings.get("assistant_name", "Assistant")
                
                # Update theme if changed
                new_theme = new_settings.get("ui", {}).get("theme", "textual-dark")
                if new_theme != self.theme:
                    self.theme = new_theme
                
                # Show confirmation
                chat_view.add_message("system", "✅ Settings saved successfully!")
        
        self.push_screen(SettingsScreen(self.settings, self.settings_file), check_settings)
    
    async def on_shutdown(self):
        """Cleanup on shutdown."""
        await self.openrouter.close()


def main():
    """Main entry point."""
    # Configure logging to file only (not console, since we're in a TUI)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('prattle.log')
        ]
    )
    
    logging.info("Starting Prattle application")
    
    try:
        app = PrattleApp()
        app.run()
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

"""Main Textual TUI application."""
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Input, ListView, ListItem, Label, OptionList, Markdown
from textual.widgets.option_list import Option
from textual.reactive import reactive
from textual import events, on, work
from textual.worker import Worker
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
    MAX_MEMORY_ENTRIES
)
from .utils import parse_message_history, format_token_usage


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
        height: 1fr;
        background: $surface;
        padding: 0;
    }
    
    #chat-list > ListItem {
        background: $surface;
        color: $text;
        padding: 1 2;
        height: auto;
    }
    
    #chat-list > ListItem:hover {
        background: $boost;
    }
    
    #chat-list > ListItem.-highlight {
        background: $accent;
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
        
        # Try to get API key from settings first, then environment
        api_key = self.settings.get("openrouter_api_key") or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            # Allow app to start even without API key - user can set it in settings
            api_key = "dummy_key_to_be_set_in_settings"
        
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
            "openrouter_api_key": "",
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
                    yield Input(placeholder="Type a message or /command...", id="chat-input")
        
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
        
        # Start auto-update timer
        self.set_interval(300, self._check_title_update)  # 5 minutes
    
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
                # Add icon/bullet prefix
                if chat.folder:
                    display = f"📁 {chat.folder}/{chat.title}"
                else:
                    display = f"• {chat.title}"
                
                # Prefix chat ID with 'chat-' to make it a valid Textual ID
                item = ListItem(Label(display), id=f"chat-{chat.chat_id}")
                await chat_list.mount(item)
    
    async def _create_new_chat(self):
        """Create a new chat."""
        # Use the default model from settings for new chats
        default_model = self.settings.get("default_model", DEFAULT_CHAT_MODEL)
        
        chat_id, _ = self.chat_file.create_new_chat(
            title="New Chat",
            model=default_model
        )
        
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
            return
        
        self.current_chat_id = chat_id
        metadata = chat_data["metadata"]
        self.current_model = metadata.model
        
        # Clear and populate chat view
        chat_view = self.query_one(ChatView)
        chat_view.clear_messages()
        
        # Parse and display messages from full history
        full_history = chat_data["full_history"]
        
        # Parse messages using utility function
        for role, content in parse_message_history(full_history):
            chat_view.add_message(role, content)
        
        # Update status
        status_bar = self.query_one(StatusBar)
        status_bar.update_stats(self.current_model)
    
    @on(Input.Submitted)
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle message submission."""
        message = event.value.strip()
        if not message:
            return
        
        # Clear input
        event.input.value = ""
        
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
    
    async def _send_message(self, user_message: str):
        """
        Send message to API and stream response.
        
        Builds context from system prompt, memories, compact context, and history,
        then streams the response and saves to chat file.
        
        Args:
            user_message: The user's message to send
        """
        if not self.current_chat_id:
            return
        
        # Load chat history
        chat_data = self.chat_file.load_chat(self.current_chat_id)
        if not chat_data:
            return
        
        # Load memories and format context
        memories = self.memory_manager.load_memories(
            self.settings.get("max_memory_entries_in_context", MAX_MEMORY_ENTRIES)
        )
        
        # Load compact context
        compact_context = chat_data["compact_context"]
        
        # Build messages for API
        messages = []
        
        # System prompt
        messages.append({"role": "system", "content": self.system_prompt})
        
        # Memories
        if memories:
            messages.append({"role": "system", "content": f"# Relevant Memories\n\n{memories}"})
        
        # Compact context (previous conversation summary) - only if exists
        if compact_context:
            messages.append({"role": "system", "content": f"# Previous Context\n\n{compact_context}"})
        
        # Add conversation history from this chat
        full_history = chat_data["full_history"]
        if full_history.strip():
            # Parse history using utility function
            for role, content in parse_message_history(full_history):
                messages.append({"role": role, "content": content})
        
        # Current user message
        messages.append({"role": "user", "content": user_message})
        
        # Stream response
        chat_view = self.query_one(ChatView)
        response_content = ""
        usage = None
        
        # Add placeholder for assistant message
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        assistant_msg = chat_view.add_message("assistant", "█", timestamp)
        
        try:
            async for content, msg_usage in self.openrouter.chat_completion(
                messages,
                self.current_model,
                stream=True
            ):
                if content:
                    response_content += content
                    # Update the message in real-time with streaming content
                    chat_view.update_last_message(response_content + "█")
                
                if msg_usage:
                    usage = msg_usage
            
            # Remove cursor and show final content
            chat_view.update_last_message(response_content)
            
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
            chat_view.add_message("system", f"Error: {str(e)}")
    
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
        
        # Append to full history
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        full_history += f"\n\n## User `[{timestamp}]`\n\n{user_msg}\n\n## Assistant `[{timestamp}]`\n\n{assistant_msg}\n"
        
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
        # Count messages - support both old and new formats
        message_count = full_history.count("**User:**") + full_history.count("## User")
        
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
            chat_input = self.query_one("#chat-input", Input)
            
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
                chat_input = self.query_one("#chat-input", Input)
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
    app = PrattleApp()
    app.run()


if __name__ == "__main__":
    main()

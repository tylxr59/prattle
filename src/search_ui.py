"""Search UI screen for searching chats."""
import logging
from typing import Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical
from textual.widgets import Input, Label, ListView, ListItem, Static
from textual import on
from textual.message import Message


class SearchResult(Message):
    """Message sent when a search result is selected."""
    
    def __init__(self, mode: str, chat_id: Optional[str], message_index: Optional[int], chat_file: Optional[str] = None):
        """Initialize search result.
        
        Args:
            mode: "current" or "all"
            chat_id: ID of the chat (for "all" mode)
            message_index: Index of the message in the chat (for "current" mode)
            chat_file: File name of the chat (for "all" mode)
        """
        super().__init__()
        self.mode = mode
        self.chat_id = chat_id
        self.message_index = message_index
        self.chat_file = chat_file


class SearchScreen(Screen):
    """Modal screen for searching chats."""
    
    CSS = """
    SearchScreen {
        align: center middle;
    }
    
    #search-dialog {
        width: 90;
        height: 70%;
        border: thick $accent;
        background: $surface;
        padding: 1;
    }
    
    #search-title {
        width: 100%;
        text-align: center;
        background: $accent;
        padding: 1;
        margin-bottom: 1;
    }
    
    #search-input {
        width: 100%;
        margin-bottom: 1;
    }
    
    #search-results {
        width: 100%;
        height: 1fr;
        border: solid $accent;
    }
    
    #search-results ListItem {
        height: auto;
        padding: 1;
    }
    
    #search-results ListItem:hover {
        background: $boost;
    }
    
    #search-results ListItem.-highlight {
        background: $accent;
    }
    
    .result-title {
        color: $text;
        text-style: bold;
    }
    
    .result-snippet {
        color: $text-muted;
    }
    
    #search-status {
        width: 100%;
        text-align: center;
        padding: 1;
        color: $text-muted;
    }
    """
    
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, mode: str, chat_messages: Optional[list] = None, chat_file_handler = None, current_chat_id: Optional[str] = None):
        """Initialize search screen.
        
        Args:
            mode: "current" to search current chat, "all" to search all chats
            chat_messages: List of ChatMessage objects (for "current" mode)
            chat_file_handler: ChatFile instance (for "all" mode)
            current_chat_id: Current chat ID
        """
        super().__init__()
        self.mode = mode
        self.chat_messages = chat_messages or []
        self.chat_file_handler = chat_file_handler
        self.current_chat_id = current_chat_id
        self.search_results = []
    
    def compose(self) -> ComposeResult:
        """Compose the search UI."""
        title = "🔍 Search Current Chat" if self.mode == "current" else "🔍 Search All Chats"
        
        with Container(id="search-dialog"):
            yield Label(title, id="search-title")
            yield Input(placeholder="Enter search query...", id="search-input")
            yield ListView(id="search-results")
            yield Label("Type to search", id="search-status")
    
    def on_mount(self) -> None:
        """Focus the search input when mounted."""
        search_input = self.query_one("#search-input", Input)
        search_input.focus()
    
    @on(Input.Changed, "#search-input")
    async def on_search_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        query = event.value.strip()
        
        if not query:
            # Clear results
            results_list = self.query_one("#search-results", ListView)
            await results_list.clear()
            status = self.query_one("#search-status", Label)
            status.update("Type to search")
            return
        
        # Perform search
        await self._perform_search(query)
    
    async def _perform_search(self, query: str):
        """Perform the search based on mode."""
        status = self.query_one("#search-status", Label)
        status.update("Searching...")
        
        results_list = self.query_one("#search-results", ListView)
        await results_list.clear()
        self.search_results = []
        
        if self.mode == "current":
            await self._search_current_chat(query, results_list)
        else:
            await self._search_all_chats(query, results_list)
        
        # Update status
        count = len(self.search_results)
        if count == 0:
            status.update("No results found")
        else:
            status.update(f"Found {count} result(s)")
    
    async def _search_current_chat(self, query: str, results_list: ListView):
        """Search within current chat messages."""
        query_lower = query.lower()
        
        for i, msg in enumerate(self.chat_messages):
            if query_lower in msg.content_text.lower():
                # Extract snippet
                content = msg.content_text
                idx = content.lower().find(query_lower)
                start = max(0, idx - 50)
                end = min(len(content), idx + len(query) + 50)
                snippet = content[start:end]
                
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
                
                role_label = "You" if msg.role == "user" else "Assistant"
                
                # Create list item
                item = ListItem(
                    Static(f"[bold]Message {i + 1}[/] ({role_label})\n[dim]{snippet.strip()}[/]")
                )
                item.set_class(True, "search-result-item")
                await results_list.mount(item)
                
                # Store result info
                self.search_results.append({
                    "mode": "current",
                    "message_index": i,
                    "chat_id": self.current_chat_id
                })
    
    async def _search_all_chats(self, query: str, results_list: ListView):
        """Search across all chats."""
        import json
        
        if not self.chat_file_handler:
            return
        
        query_lower = query.lower()
        chats_path = self.chat_file_handler.base_path
        
        for file_path in chats_path.rglob("*.md"):
            try:
                content = file_path.read_text()
                
                if query_lower not in content.lower():
                    continue
                
                # Extract title
                title = "Unknown"
                lines = content.split('\n', 1)
                first_line = lines[0].strip()
                
                if first_line.startswith('{'):
                    try:
                        metadata = json.loads(first_line)
                        title = metadata.get('title', 'Unknown')
                    except json.JSONDecodeError:
                        pass
                elif content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 2 and "title:" in parts[1]:
                        for line in parts[1].split("\n"):
                            if line.strip().startswith("title:"):
                                title = line.split(":", 1)[1].strip().strip('"').strip("'")
                                break
                
                # Extract chat ID from filename
                chat_id = file_path.stem
                
                # Find matching lines
                lines = content.split("\n")
                match_count = 0
                for line in lines:
                    if query_lower in line.lower():
                        match_count += 1
                
                # Create list item
                item = ListItem(
                    Static(f"[bold]{title}[/]\n[dim]{file_path.name} - {match_count} match(es)[/]")
                )
                item.set_class(True, "search-result-item")
                await results_list.mount(item)
                
                # Store result info
                self.search_results.append({
                    "mode": "all",
                    "chat_id": chat_id,
                    "chat_file": file_path.name,
                    "title": title
                })
                
            except Exception as e:
                logging.warning(f"Error searching file {file_path}: {e}")
                continue
    
    @on(ListView.Selected, "#search-results")
    def on_result_selected(self, event: ListView.Selected) -> None:
        """Handle result selection."""
        selected_index = event.list_view.index
        
        if selected_index is not None and selected_index < len(self.search_results):
            result = self.search_results[selected_index]
            
            # Send message with selected result
            self.post_message(SearchResult(
                mode=result["mode"],
                chat_id=result.get("chat_id"),
                message_index=result.get("message_index"),
                chat_file=result.get("chat_file")
            ))
            
            # Close the search screen
            self.dismiss()
    
    def action_cancel(self) -> None:
        """Cancel and close the search screen."""
        self.dismiss()

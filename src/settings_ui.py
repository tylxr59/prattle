"""Settings UI screen for managing configuration."""
import json
import logging
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Header, Footer, Static, Input, Button, Label, Select
from textual import on

from .constants import (
    MIN_UPDATE_INTERVAL,
    MAX_TITLE_UPDATE_INTERVAL,
    MAX_MEMORY_UPDATE_INTERVAL,
    MIN_SIDEBAR_WIDTH,
    MAX_SIDEBAR_WIDTH,
    MIN_MEMORY_ENTRIES,
    MAX_MEMORY_ENTRIES_LIMIT
)


class SettingsScreen(Screen):
    """Modal screen for editing settings."""
    
    CSS = """
    SettingsScreen {
        align: center middle;
    }
    
    #settings-dialog {
        width: 80;
        height: auto;
        max-height: 90%;
        border: thick $accent;
        background: $surface;
        padding: 1;
    }
    
    #settings-title {
        width: 100%;
        text-align: center;
        background: $accent;
        padding: 1;
        margin-bottom: 1;
    }
    
    #settings-content {
        height: auto;
        max-height: 40;
        padding: 1;
    }
    
    .setting-row {
        height: auto;
        padding: 0 1;
        margin: 1 0;
    }
    
    .setting-label {
        width: 30;
        padding: 1 0;
    }
    
    .setting-input {
        width: 1fr;
    }
    
    #button-row {
        height: auto;
        width: 100%;
        align: center middle;
        padding: 1;
    }
    
    Button {
        margin: 0 1;
    }
    """
    
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, settings: dict, settings_file: Path):
        """Initialize settings screen."""
        super().__init__()
        self.settings = settings.copy()
        self.settings_file = Path(settings_file)
        
        # Store input widgets for later access
        self.inputs: dict[str, Input] = {}
    
    def compose(self) -> ComposeResult:
        """Compose the settings UI."""
        with Container(id="settings-dialog"):
            yield Label("⚙️  Settings", id="settings-title")
            
            with ScrollableContainer(id="settings-content"):
                # API Key
                with Horizontal(classes="setting-row"):
                    yield Label("OpenRouter API Key:", classes="setting-label")
                    api_key_input = Input(
                        value=self.settings.get("openrouter_api_key", ""),
                        password=True,
                        placeholder="sk-or-...",
                        classes="setting-input",
                        id="api_key"
                    )
                    self.inputs["openrouter_api_key"] = api_key_input
                    yield api_key_input
                
                yield Label("💡 Get your API key at: https://openrouter.ai/keys", classes="setting-row")
                
                # Default Model
                with Horizontal(classes="setting-row"):
                    yield Label("Default Model:", classes="setting-label")
                    model_input = Input(
                        value=self.settings.get("default_model", "anthropic/claude-3.5-sonnet"),
                        placeholder="model-name",
                        classes="setting-input",
                        id="default_model"
                    )
                    self.inputs["default_model"] = model_input
                    yield model_input
                
                # User Name
                with Horizontal(classes="setting-row"):
                    yield Label("User Name:", classes="setting-label")
                    user_name_input = Input(
                        value=self.settings.get("user_name", "You"),
                        placeholder="You",
                        classes="setting-input",
                        id="user_name"
                    )
                    self.inputs["user_name"] = user_name_input
                    yield user_name_input
                
                # Assistant Name
                with Horizontal(classes="setting-row"):
                    yield Label("Assistant Name:", classes="setting-label")
                    assistant_name_input = Input(
                        value=self.settings.get("assistant_name", "Assistant"),
                        placeholder="Assistant",
                        classes="setting-input",
                        id="assistant_name"
                    )
                    self.inputs["assistant_name"] = assistant_name_input
                    yield assistant_name_input
                
                # Title Update Interval
                with Horizontal(classes="setting-row"):
                    yield Label("Title Update (seconds):", classes="setting-label")
                    title_interval_input = Input(
                        value=str(self.settings.get("title_update_interval", 300)),
                        placeholder="300",
                        classes="setting-input",
                        id="title_update_interval"
                    )
                    self.inputs["title_update_interval"] = title_interval_input
                    yield title_interval_input
                
                # Memory Update Interval
                with Horizontal(classes="setting-row"):
                    yield Label("Memory Update (seconds):", classes="setting-label")
                    memory_interval_input = Input(
                        value=str(self.settings.get("memory_update_interval", 600)),
                        placeholder="600",
                        classes="setting-input",
                        id="memory_update_interval"
                    )
                    self.inputs["memory_update_interval"] = memory_interval_input
                    yield memory_interval_input
                
                # Max Memory Entries
                with Horizontal(classes="setting-row"):
                    yield Label("Max Memory Entries:", classes="setting-label")
                    memory_entries_input = Input(
                        value=str(self.settings.get("max_memory_entries_in_context", 10)),
                        placeholder="10",
                        classes="setting-input",
                        id="max_memory_entries"
                    )
                    self.inputs["max_memory_entries_in_context"] = memory_entries_input
                    yield memory_entries_input
                
                # UI Settings
                yield Label("", classes="setting-row")
                yield Label("🎨 UI Settings", classes="setting-row")
                
                with Horizontal(classes="setting-row"):
                    yield Label("Sidebar Width:", classes="setting-label")
                    sidebar_width_input = Input(
                        value=str(self.settings.get("ui", {}).get("sidebar_width", 30)),
                        placeholder="30",
                        classes="setting-input",
                        id="sidebar_width"
                    )
                    self.inputs["sidebar_width"] = sidebar_width_input
                    yield sidebar_width_input
                
                with Horizontal(classes="setting-row"):
                    yield Label("Syntax Theme:", classes="setting-label")
                    theme_input = Input(
                        value=self.settings.get("ui", {}).get("syntax_theme", "monokai"),
                        placeholder="monokai",
                        classes="setting-input",
                        id="syntax_theme"
                    )
                    self.inputs["syntax_theme"] = theme_input
                    yield theme_input
                
                with Horizontal(classes="setting-row"):
                    yield Label("TUI Theme:", classes="setting-label")
                    tui_theme_input = Input(
                        value=self.settings.get("ui", {}).get("theme", "textual-dark"),
                        placeholder="textual-dark",
                        classes="setting-input",
                        id="tui_theme"
                    )
                    self.inputs["tui_theme"] = tui_theme_input
                    yield tui_theme_input
                
                yield Label("💡 Available themes: textual-dark, textual-light, nord, gruvbox, catppuccin, dracula, monokai, solarized-light", classes="setting-row")
            
            # Buttons
            with Horizontal(id="button-row"):
                yield Button("Save", variant="success", id="save-button")
                yield Button("Cancel", variant="default", id="cancel-button")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-button":
            self.save_settings()
        elif event.button.id == "cancel-button":
            self.cancel_settings()
    
    def save_settings(self):
        """Save settings and close."""
        # Capture API key but don't save to settings.json (security)
        api_key = self.inputs["openrouter_api_key"].value
        
        # Update settings from inputs (excluding API key)
        self.settings["default_model"] = self.inputs["default_model"].value
        self.settings["user_name"] = self.inputs["user_name"].value
        self.settings["assistant_name"] = self.inputs["assistant_name"].value
        
        try:
            value = int(self.inputs["title_update_interval"].value)
            self.settings["title_update_interval"] = max(MIN_UPDATE_INTERVAL, min(MAX_TITLE_UPDATE_INTERVAL, value))
        except ValueError:
            self.settings["title_update_interval"] = 300
        
        try:
            value = int(self.inputs["memory_update_interval"].value)
            self.settings["memory_update_interval"] = max(MIN_UPDATE_INTERVAL, min(MAX_MEMORY_UPDATE_INTERVAL, value))
        except ValueError:
            self.settings["memory_update_interval"] = 600
        
        try:
            value = int(self.inputs["max_memory_entries_in_context"].value)
            self.settings["max_memory_entries_in_context"] = max(MIN_MEMORY_ENTRIES, min(MAX_MEMORY_ENTRIES_LIMIT, value))
        except ValueError:
            self.settings["max_memory_entries_in_context"] = 10
        
        # Update UI settings
        if "ui" not in self.settings:
            self.settings["ui"] = {}
        
        try:
            value = int(self.inputs["sidebar_width"].value)
            self.settings["ui"]["sidebar_width"] = max(MIN_SIDEBAR_WIDTH, min(MAX_SIDEBAR_WIDTH, value))
        except ValueError:
            self.settings["ui"]["sidebar_width"] = 30
        
        self.settings["ui"]["syntax_theme"] = self.inputs["syntax_theme"].value
        self.settings["ui"]["theme"] = self.inputs["tui_theme"].value
        
        # Remove API key if it exists in settings (should not be there)
        if "openrouter_api_key" in self.settings:
            del self.settings["openrouter_api_key"]
        
        # Save to file
        try:
            self.settings_file.write_text(json.dumps(self.settings, indent=2))
            logging.info("Settings saved successfully")
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")
            # Continue anyway to try to save API key
        
        # Also update .env with API key if provided
        if api_key and api_key.strip():
            env_file = self.settings_file.parent / ".env"
            
            try:
                if env_file.exists():
                    # Update existing .env
                    lines = env_file.read_text().split("\n")
                    new_lines = []
                    updated = False
                    
                    for line in lines:
                        if line.startswith("OPENROUTER_API_KEY="):
                            new_lines.append(f"OPENROUTER_API_KEY={api_key}")
                            updated = True
                        else:
                            new_lines.append(line)
                    
                    if not updated:
                        new_lines.append(f"OPENROUTER_API_KEY={api_key}")
                    
                    env_file.write_text("\n".join(new_lines))
                else:
                    env_file.write_text(f"OPENROUTER_API_KEY={api_key}\n")
                
                logging.info("API key saved to .env file")
            except Exception as e:
                logging.error(f"Failed to save API key to .env: {e}")
        
        # Return to main app with settings
        self.dismiss(self.settings)
    
    def cancel_settings(self):
        """Cancel and close without saving."""
        self.dismiss(None)
    
    def action_cancel(self):
        """Cancel via escape key."""
        self.dismiss(None)

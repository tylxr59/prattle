#!/usr/bin/env python3
"""
Prattle - Terminal AI Chat Client

Main entry point that handles initialization and launches the TUI application.
"""
import sys
import json
from pathlib import Path


def check_python_version():
    """Ensure Python 3.10+ is being used."""
    if sys.version_info < (3, 10):
        print(f"❌ Error: Python 3.10 or higher is required")
        print(f"   Current version: {sys.version_info.major}.{sys.version_info.minor}")
        sys.exit(1)


def check_dependencies():
    """Check if required dependencies are installed."""
    missing_deps = []
    
    try:
        import textual
    except ImportError:
        missing_deps.append("textual")
    
    try:
        import httpx
    except ImportError:
        missing_deps.append("httpx")
    
    try:
        import dotenv
    except ImportError:
        missing_deps.append("python-dotenv")
    
    try:
        import yaml
    except ImportError:
        missing_deps.append("pyyaml")
    
    if missing_deps:
        print("❌ Missing required dependencies!\n")
        print("Prattle requires the following packages:")
        for dep in missing_deps:
            print(f"   • {dep}")
        print("\n📦 To install dependencies:\n")
        
        # Check if we're in a virtual environment
        in_venv = hasattr(sys, 'real_prefix') or (
            hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
        )
        
        if not in_venv:
            print("⚠️  You're not in a virtual environment!")
            print("   It's recommended to use one (especially on Arch Linux):\n")
            print("   # Create and activate virtual environment")
            print("   python3 -m venv venv")
            print("   source venv/bin/activate\n")
        
        print("   # Install Prattle with dependencies")
        print("   pip install -e .\n")
        print("   # Then run Prattle")
        print("   python prattle.py\n")
        
        sys.exit(1)


def ensure_settings():
    """Create settings.json if it doesn't exist."""
    settings_file = Path("settings.json")
    
    if settings_file.exists():
        return
    
    print("⚙️  Creating default settings.json...")
    
    default_settings = {
        "openrouter_api_key": "",
        "default_model": "anthropic/claude-3.5-sonnet",
        "title_update_interval": 300,
        "memory_update_interval": 600,
        "max_memory_entries_in_context": 10,
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
            "sidebar_width": 30
        }
    }
    
    settings_file.write_text(json.dumps(default_settings, indent=2))
    print("✓ Created settings.json")
    print("\n⚠️  Please configure your OpenRouter API key:")
    print("   - Run Prattle and use /settings command (or press Ctrl+,)")
    print("   - Or edit settings.json manually\n")


def ensure_directories():
    """Create necessary directories if they don't exist."""
    dirs = ["chats", "context"]
    
    for dir_name in dirs:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
    
    # Create default context files if they don't exist
    prompt_file = Path("context/prompt.md")
    if not prompt_file.exists():
        prompt_file.write_text("""You are a helpful AI assistant integrated into a terminal chat application called Prattle.

Be concise, direct, and helpful in your responses. Format code with proper syntax highlighting using markdown code blocks. When explaining complex topics, break them down into clear steps.

You have access to conversation memories that track user preferences, ongoing projects, and important context from previous chats. Use this information to provide more personalized and relevant assistance.
""")
    
    memories_file = Path("context/memories.md")
    if not memories_file.exists():
        memories_file.write_text("""# Agent Memories

This file contains important information extracted from conversations to provide better context in future chats.

## User Preferences
<!-- AI will populate this section -->

## Ongoing Projects
<!-- AI will populate this section -->

## Important Context
<!-- AI will populate this section -->
""")


def main():
    """Main entry point."""
    # Check Python version first
    check_python_version()
    
    # Check dependencies before proceeding
    check_dependencies()
    
    # Ensure we're in the right directory (where this script is)
    script_dir = Path(__file__).parent.resolve()
    import os
    os.chdir(script_dir)
    
    # Add src to Python path
    sys.path.insert(0, str(script_dir / "src"))
    
    # Ensure settings and directories exist
    ensure_settings()
    ensure_directories()
    
    # Import and run the app
    try:
        from src.app import main as app_main
        
        print("🚀 Starting Prattle...\n")
        app_main()
    
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

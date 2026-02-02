# Quick Start Guide

## Setup

1. **Install Prattle:**
   ```bash
   # Create virtual environment (recommended)
   python3 -m venv venv
   source venv/bin/activate
   
   # Install dependencies
   pip install -e .
   ```

2. **Configure your API key:**
   
   Prattle automatically creates `settings.json` on first run. You need to add your OpenRouter API key:
   
   - Get your key at: https://openrouter.ai/keys
   - Run Prattle: `python prattle.py`
   - Use `/settings` command or press `Ctrl+,`
   - Enter your API key and save

## Running Prattle

```bash
# With virtual environment (recommended)
source venv/bin/activate
python prattle.py

# Or make executable and run directly
chmod +x prattle.py
./prattle.py
```

**What happens on first run:**
- Prattle checks if dependencies are installed
- Creates `settings.json` automatically
- Sets up required directories
- Prompts you to configure API key

## Essential Commands

- `/settings` - Configure API key and preferences
- `/help` - Show all commands
- `/models` - Browse and switch AI models
- `/move <folder>` - Organize chats into folders

## Keyboard Shortcuts

- `Ctrl+,` - Open settings
- `Ctrl+N` - New chat
- `Ctrl+Enter` - Send message
- `Ctrl+Q` - Quit

## Troubleshooting

**"API key not found" error:**
- Run `/settings` command
- Enter your OpenRouter API key
- Save and restart

**Missing dependencies error:**
- Prattle will tell you exactly what's missing
- Follow the instructions it provides to install dependencies
- If using virtual environment: activate it first with `source venv/bin/activate`
- Then run: `pip install -e .`

**Settings not saving:**
- Check file permissions on `settings.json`
- Make sure you're running from the project directory

## File Locations

- Chats: `chats/` (organized by folders if you use `/move`)
- Settings: `settings.json` (not tracked in git)
- Memories: `context/memories.md`
- System prompt: `context/prompt.md`

## Arch Linux Note

This project uses a Python virtual environment to avoid conflicts with system packages. Always activate the venv before running:

```bash
source venv/bin/activate
```

Or use the convenience script: `./run.sh`

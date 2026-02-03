# Prattle

/'prætəl/  - *speak (about unimportant matters) rapidly and incessantly*

A terminal-based AI chat client with persistent memory and intelligent context management.

**This project is in extremely early development. Things will break, UIs will change, and chats might not be forward compatible. Don't expect this to be perfect.**

## Features

- 🖥️ **Beautiful TUI** - Clean terminal interface built with Textual
- 💾 **Persistent Chats** - All conversations saved with UUID-based filenames
- 🧠 **Smart Memory** - AI automatically extracts and remembers important context
- 📊 **Cost Tracking** - Real-time token usage and cost monitoring
- 🗂️ **Folder Organization** - Organize chats into folders with `/move`
- 🔀 **Chat Branching** - Create alternate timelines with `/branch`
- 🗜️ **Context Compression** - Summarize long conversations with `/compact`
- 🔍 **Full-text Search** - Search across all your chats with `/search`
- 🎯 **Dynamic Titles** - Auto-generated and updated chat titles
- 🔧 **Model Switching** - Change models mid-conversation with `/switch`

## Installation

### Quick Start (Recommended)

```bash
# Clone the repository
git clone https://github.com/tylxr59/prattle.git
cd prattle

# Create virtual environment (recommended, especially on Arch Linux)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .

# Set up your API key
cp .env.example .env
# Edit .env and add your OpenRouter API key
nano .env  # or use your preferred editor

# Run Prattle (it auto-generates config on first run)
python prattle.py
```

### Configuration

**API Key Setup:**
- Get your API key from [OpenRouter](https://openrouter.ai/keys)
- Add it to `.env` file: `OPENROUTER_API_KEY=your_key_here`
- Never commit your `.env` file to version control (it's in `.gitignore`)

On first run, Prattle will automatically:
- Create `settings.json` with default configuration (no API key stored here for security)
- Set up required directories (`chats/`, `context/`)
- Generate default system prompt and memories files

You can also configure your API key through the UI with `Ctrl+,` (Settings).

## License

0BSD License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.

## Acknowledgments

- Built with [Textual](https://textual.textualize.io/) - amazing TUI framework
- Powered by [OpenRouter](https://openrouter.ai/) - unified LLM API 
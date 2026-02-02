# Convenient Aliases for Prattle

Add these to your shell configuration (~/.bashrc, ~/.zshrc, etc.) for easier access:

```bash
# Prattle alias - run from anywhere
alias prattle='python /path/to/prattle/prattle.py'

# Or if you have a virtual environment
alias prattle='source /path/to/prattle/venv/bin/activate && python /path/to/prattle/prattle.py'
```

## Quick Setup Example

```bash
# In your shell config file
echo 'alias prattle="cd ~/git/prattle && source venv/bin/activate && python prattle.py"' >> ~/.bashrc
source ~/.bashrc

# Now you can run from anywhere:
prattle
```

## Alternative: Add to PATH

Make prattle.py executable and add to your PATH:

```bash
chmod +x prattle.py

# Add to ~/.bashrc or ~/.zshrc
export PATH="$PATH:/path/to/prattle"

# Now you can run:
prattle.py
```

"""Utility functions used across the application."""
import re
import logging
from typing import Tuple, List, Optional

from .constants import USER_HEADER, ASSISTANT_HEADER


def escape_message_headers(text: str) -> str:
    """Escape message headers in user content to prevent parsing issues.
    
    Replaces '## User' and '## Assistant' at the start of lines with a zero-width space
    to prevent them from being interpreted as message separators.
    
    Args:
        text: Message content that may contain header-like patterns
        
    Returns:
        Text with headers escaped
    """
    # Use zero-width space (U+200B) after ## to break the pattern
    text = re.sub(r'^## User', '##\u200B User', text, flags=re.MULTILINE)
    text = re.sub(r'^## Assistant', '##\u200B Assistant', text, flags=re.MULTILINE)
    return text


def unescape_message_headers(text: str) -> str:
    """Unescape message headers when displaying content.
    
    Args:
        text: Message content with escaped headers
        
    Returns:
        Text with headers unescaped
    """
    # Remove zero-width space
    text = text.replace('##\u200B User', '## User')
    text = text.replace('##\u200B Assistant', '## Assistant')
    return text


def strip_timestamp(text: str) -> str:
    """
    Remove timestamp from text like `[2026-02-02 14:33:43]`.
    
    Args:
        text: Text that may contain a timestamp
        
    Returns:
        Text with timestamp removed
    """
    if text.startswith("`[") and "]`" in text:
        return text.split("]`", 1)[1].strip() if "]`" in text else text
    return text


def parse_message_history(history: str) -> List[Tuple[str, str, str]]:
    """Parse chat history into list of (role, content, token_info) tuples.
    
    Uses regex pattern matching to identify message headers with timestamps,
    which prevents user content containing '## User' or '## Assistant' from
    being incorrectly parsed as message boundaries.
    
    Args:
        history: Full chat history in markdown format
        
    Returns:
        List of (role, content, token_info) tuples where token_info is empty string if not present
    """
    messages = []
    
    # Pattern: ## User `[YYYY-MM-DD HH:MM:SS]` or ## Assistant `[YYYY-MM-DD HH:MM:SS]`
    # This ensures we only match actual message headers with timestamps, not user content
    message_pattern = re.compile(
        r'^## (User|Assistant) `\[[\d\-: ]+\]`',
        re.MULTILINE
    )
    
    # Find all message headers
    matches = list(message_pattern.finditer(history))
    
    if not matches:
        # No messages found
        return messages
    
    for i, match in enumerate(matches):
        role = match.group(1).lower()  # 'User' or 'Assistant' -> 'user' or 'assistant'
        start = match.end()  # Content starts after the header line
        
        # Find where this message ends (start of next message, or end of string)
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(history)
        
        # Extract content
        content = history[start:end].strip()
        
        # Extract token/cost info lines and remove from content
        content_lines = []
        token_info = ""
        for line in content.split('\n'):
            if line.startswith('*💬') and 'tokens' in line:
                token_info = line.strip('*').strip()  # Remove asterisks and whitespace
                continue
            content_lines.append(line)
        
        content = '\n'.join(content_lines).strip()
        
        # Unescape any message headers that were in the content
        content = unescape_message_headers(content)
        
        if content:
            messages.append((role, content, token_info))
    
    return messages


def format_token_usage(prompt_tokens: int, completion_tokens: int, total_cost: float, model: str, tokens_per_second: Optional[float] = None) -> str:
    """Format token usage info for display.
    
    Args:
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        total_cost: Total cost in dollars
        model: Model name/ID used (optional)
        tokens_per_second: Generation speed in tokens/sec (optional)
        
    Returns:
        Formatted string
    """
    total = prompt_tokens + completion_tokens
    model_str = f" • 🤖 {model}" if model else ""
    speed_str = f" • ⚡ {tokens_per_second:.1f} tps" if tokens_per_second else ""
    return (
        f"💬 {total} tokens ({prompt_tokens} prompt + {completion_tokens} completion) "
        f"• 💰 ${total_cost:.6f}{speed_str}{model_str}"
    )

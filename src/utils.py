"""Utility functions used across the application."""
import re
from typing import Tuple, List


def strip_timestamp(text: str) -> str:
    """
    Remove timestamp from text like `[2026-02-02 14:33:43 UTC]`.
    
    Args:
        text: Text that may contain a timestamp
        
    Returns:
        Text with timestamp removed
    """
    if text.startswith("`[") and "]`" in text:
        return text.split("]`", 1)[1].strip() if "]`" in text else text
    return text


def parse_message_history(history: str) -> List[Tuple[str, str]]:
    """
    Parse chat history into list of (role, content) tuples.
    
    Args:
        history: Full chat history in markdown format
        
    Returns:
        List of (role, content) tuples
    """
    messages = []
    lines = history.split("\n")
    current_role = None
    current_content = []
    
    for line in lines:
        # Skip token/cost info lines
        if line.startswith("*💬") and "tokens" in line:
            continue
        
        # Check for both old format (**User:**) and new format (## User)
        if line.startswith("**User:**") or line.startswith("## User"):
            # Save previous message if exists
            if current_role and current_content:
                content_text = "\n".join(current_content).strip()
                if content_text:
                    messages.append((current_role, content_text))
            
            # Start new user message
            current_role = "user"
            if line.startswith("**User:**"):
                content = line.replace("**User:**", "").strip()
            else:
                content = line.replace("## User", "").strip()
            content = strip_timestamp(content)
            current_content = [content] if content else []
            
        elif line.startswith("**Assistant:**") or line.startswith("## Assistant"):
            # Save previous message if exists
            if current_role and current_content:
                content_text = "\n".join(current_content).strip()
                if content_text:
                    messages.append((current_role, content_text))
            
            # Start new assistant message
            current_role = "assistant"
            if line.startswith("**Assistant:**"):
                content = line.replace("**Assistant:**", "").strip()
            else:
                content = line.replace("## Assistant", "").strip()
            content = strip_timestamp(content)
            current_content = [content] if content else []
            
        elif current_role:
            # Continue current message - preserve blank lines for markdown formatting
            current_content.append(line)
    
    # Don't forget the last message
    if current_role and current_content:
        content_text = "\n".join(current_content).strip()
        if content_text:
            messages.append((current_role, content_text))
    
    return messages


def format_token_usage(prompt_tokens: int, completion_tokens: int, total_cost: float, model: str) -> str:
    """
    Format token usage info for display.
    
    Args:
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        total_cost: Total cost in dollars
        model: Model name/ID used (optional)
        
    Returns:
        Formatted string
    """
    total = prompt_tokens + completion_tokens
    model_str = f" • 🤖 {model}" if model else ""
    return (
        f"💬 {total} tokens ({prompt_tokens} prompt + {completion_tokens} completion) "
        f"• 💰 ${total_cost:.6f}{model_str}"
    )

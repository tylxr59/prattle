"""OpenRouter API client for chat completions and model management."""
import httpx
import json
from typing import AsyncIterator, Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class ModelInfo:
    """Information about an OpenRouter model."""
    id: str
    name: str
    description: str
    context_length: int
    prompt_cost: float  # Per million tokens
    completion_cost: float  # Per million tokens
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "ModelInfo":
        """Create from OpenRouter API response."""
        pricing = data.get("pricing", {})
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data.get("description", ""),
            context_length=data.get("context_length", 0),
            prompt_cost=float(pricing.get("prompt", 0)) * 1_000_000,
            completion_cost=float(pricing.get("completion", 0)) * 1_000_000
        )


@dataclass
class TokenUsage:
    """Token usage and cost tracking."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    total_cost: float = 0.0
    
    def update_from_response(self, usage: Dict[str, Any], model_info: ModelInfo):
        """Update tokens and costs from API response."""
        self.prompt_tokens = usage.get("prompt_tokens", 0)
        self.completion_tokens = usage.get("completion_tokens", 0)
        self.total_tokens = usage.get("total_tokens", 0)
        
        # Calculate costs
        self.prompt_cost = (self.prompt_tokens / 1_000_000) * model_info.prompt_cost
        self.completion_cost = (self.completion_tokens / 1_000_000) * model_info.completion_cost
        self.total_cost = self.prompt_cost + self.completion_cost


class OpenRouterClient:
    """Client for OpenRouter API."""
    
    BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(self, api_key: str, app_name: str = "Prattle"):
        """Initialize with API key."""
        self.api_key = api_key
        self.app_name = app_name
        self.client = httpx.AsyncClient(timeout=60.0)
        self._models_cache: Optional[List[ModelInfo]] = None
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def list_models(self, force_refresh: bool = False) -> List[ModelInfo]:
        """List all available models from OpenRouter."""
        if self._models_cache and not force_refresh:
            return self._models_cache
        
        response = await self.client.get(f"{self.BASE_URL}/models")
        response.raise_for_status()
        
        data = response.json()
        models = [ModelInfo.from_api_response(m) for m in data.get("data", [])]
        self._models_cache = models
        
        return models
    
    async def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get information about a specific model."""
        models = await self.list_models()
        for model in models:
            if model.id == model_id:
                return model
        return None
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        stream: bool = True,
        **kwargs
    ) -> AsyncIterator[tuple[str, Optional[TokenUsage]]]:
        """
        Send chat completion request.
        
        Yields tuples of (content_chunk, usage).
        Usage is only available in the final chunk.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/tylxr59/prattle",
            "X-Title": self.app_name,
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **kwargs
        }
        
        model_info = await self.get_model_info(model)
        
        if stream:
            async with self.client.stream(
                "POST",
                f"{self.BASE_URL}/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line.strip() or not line.startswith("data: "):
                        continue
                    
                    data_str = line[6:]  # Remove "data: " prefix
                    
                    if data_str == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        
                        # Extract content
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            
                            # Check for usage info (final chunk)
                            usage = None
                            if "usage" in data and model_info:
                                usage = TokenUsage()
                                usage.update_from_response(data["usage"], model_info)
                            
                            if content or usage:
                                yield content, usage
                    
                    except json.JSONDecodeError:
                        continue
        
        else:
            # Non-streaming request
            response = await self.client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            usage = None
            if "usage" in data and model_info:
                usage = TokenUsage()
                usage.update_from_response(data["usage"], model_info)
            
            yield content, usage
    
    async def generate_title(
        self,
        conversation: str,
        model: str = "anthropic/claude-3.5-haiku"
    ) -> str:
        """Generate a concise title for a conversation."""
        messages = [
            {
                "role": "system",
                "content": "Generate a concise 3-7 word title for this conversation. "
                          "Only respond with the title, nothing else."
            },
            {
                "role": "user",
                "content": f"Conversation:\n\n{conversation}"
            }
        ]
        
        title = ""
        async for content, _ in self.chat_completion(messages, model, stream=False):
            title += content
        
        return title.strip().strip('"').strip("'")
    
    async def extract_memories(
        self,
        conversation: str,
        existing_memories: str,
        model: str = "anthropic/claude-3.5-haiku"
    ) -> str:
        """Extract important information to add to memories."""
        messages = [
            {
                "role": "system",
                "content": "You are extracting important information from a conversation to save as memories. "
                          "Extract: user preferences, ongoing projects, important context, and key facts. "
                          "Format as markdown. Be concise. Only add new information not already in existing memories."
            },
            {
                "role": "user",
                "content": f"Existing memories:\n\n{existing_memories}\n\n"
                          f"New conversation:\n\n{conversation}\n\n"
                          f"Extract new important information to add to memories:"
            }
        ]
        
        memories = ""
        async for content, _ in self.chat_completion(messages, model, stream=False):
            memories += content
        
        return memories.strip()

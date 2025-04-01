"""LLM provider implementations."""

import logging
import asyncio
import random
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass

class LLMProviderError(LLMError):
    """Exception raised for provider-specific errors."""
    def __init__(self, message: str, provider: str, status_code: Optional[int] = None, response: Optional[Dict] = None):
        self.provider = provider
        self.status_code = status_code
        self.response = response
        super().__init__(f"{provider} error: {message} (status={status_code})")

class LLMProvider(ABC):
    """Base class for LLM providers."""
    
    def __init__(self, endpoint: str, model: str, timeout: int = 30):
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        
    @abstractmethod
    def build_payload(self, prompt: str) -> Dict[str, Any]:
        """Build the API request payload."""
        pass
        
    @abstractmethod
    def extract_response(self, response_data: Dict[str, Any]) -> str:
        """Extract the response text from API response."""
        pass
        
    def validate_response(self, response_data: Dict[str, Any]) -> None:
        """Validate the API response and raise appropriate errors."""
        pass

class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation."""
    
    def build_payload(self, prompt: str) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 150
        }
        
    def extract_response(self, response_data: Dict[str, Any]) -> str:
        try:
            self.validate_response(response_data)
            return response_data["choices"][0]["message"]["content"].strip()
        except KeyError as e:
            raise LLMProviderError(
                f"Invalid response format: missing {e}",
                "openai",
                response=response_data
            )
            
    def validate_response(self, response_data: Dict[str, Any]) -> None:
        if "error" in response_data:
            error = response_data["error"]
            raise LLMProviderError(
                error.get("message", "Unknown error"),
                "openai",
                status_code=error.get("code"),
                response=response_data
            )
        if "choices" not in response_data or not response_data["choices"]:
            raise LLMProviderError(
                "No choices in response",
                "openai",
                response=response_data
            )

class AnthropicProvider(LLMProvider):
    """Anthropic API provider implementation."""
    
    def build_payload(self, prompt: str) -> Dict[str, Any]:
        return {
            "model": self.model,
            "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
            "temperature": 0.7,
            "max_tokens_to_sample": 150
        }
        
    def extract_response(self, response_data: Dict[str, Any]) -> str:
        try:
            self.validate_response(response_data)
            return response_data["completion"].strip()
        except KeyError as e:
            raise LLMProviderError(
                f"Invalid response format: missing {e}",
                "anthropic",
                response=response_data
            )
            
    def validate_response(self, response_data: Dict[str, Any]) -> None:
        if "error" in response_data:
            error = response_data["error"]
            raise LLMProviderError(
                error.get("message", "Unknown error"),
                "anthropic",
                status_code=error.get("status_code"),
                response=response_data
            )
        if "completion" not in response_data:
            raise LLMProviderError(
                "No completion in response",
                "anthropic",
                response=response_data
            )

class OllamaProvider(LLMProvider):
    """Ollama API provider implementation."""
    
    def build_payload(self, prompt: str) -> Dict[str, Any]:
        return {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 150,
                "stop": ["</s>", "Human:", "Assistant:"],
                "repeat_penalty": 1.1
            }
        }
        
    def extract_response(self, response_data: Dict[str, Any]) -> str:
        try:
            self.validate_response(response_data)
            return response_data["response"].strip()
        except KeyError as e:
            raise LLMProviderError(
                f"Invalid response format: missing {e}",
                "ollama",
                response=response_data
            )
            
    def validate_response(self, response_data: Dict[str, Any]) -> None:
        if "error" in response_data:
            error = response_data["error"]
            raise LLMProviderError(
                error.get("message", "Unknown error"),
                "ollama",
                status_code=error.get("status_code"),
                response=response_data
            )
        if "response" not in response_data:
            raise LLMProviderError(
                "No response in response data",
                "ollama",
                response=response_data
            )
        if not response_data["response"].strip():
            raise LLMProviderError(
                "Empty response from model",
                "ollama",
                response=response_data
            )

class MistralProvider(LLMProvider):
    """Mistral API provider implementation."""
    
    def build_payload(self, prompt: str) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 150
        }
        
    def extract_response(self, response_data: Dict[str, Any]) -> str:
        try:
            self.validate_response(response_data)
            return response_data["choices"][0]["message"]["content"].strip()
        except KeyError as e:
            raise LLMProviderError(
                f"Invalid response format: missing {e}",
                "mistral",
                response=response_data
            )
            
    def validate_response(self, response_data: Dict[str, Any]) -> None:
        if "error" in response_data:
            error = response_data["error"]
            raise LLMProviderError(
                error.get("message", "Unknown error"),
                "mistral",
                status_code=error.get("status_code"),
                response=response_data
            )
        if "choices" not in response_data or not response_data["choices"]:
            raise LLMProviderError(
                "No choices in response",
                "mistral",
                response=response_data
            )

def get_llm_provider(name: str, endpoint: str, model: str, **kwargs) -> LLMProvider:
    """Get LLM provider instance by name."""
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
        "mistral": MistralProvider
    }
    
    provider_cls = providers.get(name.lower())
    if not provider_cls:
        raise ValueError(f"Unknown provider: {name}")
        
    return provider_cls(endpoint, model, **kwargs)

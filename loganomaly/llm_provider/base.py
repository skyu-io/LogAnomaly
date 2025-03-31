from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    def build_payload(self, prompt: str) -> dict:
        """Build API payload for the specific LLM provider."""
        pass

    @abstractmethod
    def extract_response(self, api_response: dict) -> str:
        """Extract raw reply content from API response."""
        pass
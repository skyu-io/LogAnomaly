from .base import LLMProvider

class TinyLlamaProvider(LLMProvider):
    def __init__(self, endpoint, model, timeout=10):
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout

    def build_payload(self, prompt: str) -> dict:
        return {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }

    def extract_response(self, api_response: dict) -> str:
        return api_response.get("response", "").strip()
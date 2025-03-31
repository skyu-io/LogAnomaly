from .mistral_provider import MistralProvider
from .tinyllama_provider import TinyLlamaProvider

def get_llm_provider(name, endpoint, model, timeout=10):
    if name == "mistral":
        return MistralProvider(endpoint, model, timeout)
    elif name == "tinyllama":
        return TinyLlamaProvider(endpoint, model, timeout)
    else:
        raise ValueError(f"Unsupported LLM Provider: {name}")

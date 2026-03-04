"""
Ollama LLM Client
Wrapper for communicating with the Ollama server.
"""
import ollama
from loguru import logger
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS


_client = None


def get_client() -> ollama.Client:
    """Get or create Ollama client (singleton)."""
    global _client
    if _client is None:
        _client = ollama.Client(host=OLLAMA_BASE_URL)
        logger.info(f"Ollama client connected: {OLLAMA_BASE_URL}")
    return _client


def chat(
    prompt: str,
    system: str = None,
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
) -> str:
    """
    Send a chat message to Ollama and return the response text.
    
    Args:
        prompt: User message
        system: System prompt (optional)
        model: Model name (default: from config)
        temperature: Sampling temperature (default: from config)
        max_tokens: Max response tokens (default: from config)
    
    Returns:
        Response text string
    """
    client = get_client()
    model = model or OLLAMA_MODEL
    temperature = temperature if temperature is not None else LLM_TEMPERATURE

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat(
            model=model,
            messages=messages,
            options={
                "temperature": temperature,
                "num_predict": max_tokens or LLM_MAX_TOKENS,
            },
        )
        return response["message"]["content"]
    except Exception as e:
        logger.error(f"Ollama chat error: {e}")
        raise


def test_connection() -> bool:
    """Test if Ollama server is reachable."""
    try:
        client = get_client()
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": "Respond with only: OK"}],
            options={"temperature": 0, "num_predict": 10},
        )
        result = response["message"]["content"].strip()
        logger.info(f"Ollama connection test: OK (response: {result})")
        return True
    except Exception as e:
        logger.error(f"Ollama connection test FAILED: {e}")
        return False

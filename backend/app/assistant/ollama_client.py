import httpx

from app.core.config import settings
from app.core.logging import logger


def ask_ollama(
    question: str,
    system_prompt: str,
    model: str | None = None,
    base_url: str | None = None,
) -> str | None:
    model = model or settings.ollama_model
    base = (base_url or settings.ollama_base_url).rstrip("/")

    try:
        resp = httpx.post(
            f"{base}/api/generate",
            json={
                "model": model,
                "prompt": question,
                "system": system_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 500,
                },
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("response", "").strip()
    except httpx.ConnectError:
        logger.warning("Ollama not available at %s", base)
        return None
    except Exception as e:
        logger.warning("Ollama request failed: %s", e)
        return None


def is_ollama_available(base_url: str | None = None) -> bool:
    base = (base_url or settings.ollama_base_url).rstrip("/")
    try:
        resp = httpx.get(f"{base}/api/tags", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False

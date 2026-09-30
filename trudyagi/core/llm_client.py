"""
trudyagi/core/llm_client.py — OpenAI-compatible LLM client

Works with:
    - OpenAI (https://api.openai.com/v1/)
    - Anthropic via OpenAI-compat proxy
    - Z.ai GLM (https://open.bigmodel.cn/api/paas/v4/)
    - Ollama local (http://localhost:11434/v1/)
    - Any OpenAI-compatible endpoint

Required env vars:
    LLM_API_KEY     — API key
    LLM_BASE_URL    — full URL including /v1/ suffix
    LLM_MODEL       — model name (e.g., gpt-4o-mini, glm-4-flash, llama3.2)

Optional:
    LLM_MAX_TOKENS  — default 1500
    LLM_TEMPERATURE — default 0.3 (low for structured output)
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional


class LLMClient:
    """Minimal OpenAI-compatible client using only stdlib urllib."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
        self.max_tokens = max_tokens or int(os.environ.get("LLM_MAX_TOKENS", "1500"))
        self.temperature = temperature or float(os.environ.get("LLM_TEMPERATURE", "0.3"))

        if not self.api_key:
            raise ValueError("LLM_API_KEY not set. Run: trudyagi.py init")
        if not self.base_url:
            raise ValueError("LLM_BASE_URL not set. Run: trudyagi.py init")

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request. Returns the assistant message text."""
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "response_format": {"type": "text"},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                response = json.loads(resp.read().decode("utf-8"))
                return response["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"LLM API error {e.code}: {err_body}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"LLM API network error: {e.reason}") from None
        except (KeyError, json.JSONDecodeError) as e:
            raise RuntimeError(f"LLM API response parse error: {e}") from None

    def is_alive(self) -> bool:
        """Quick health check — send a 1-token 'ping' request."""
        try:
            url = f"{self.base_url}/chat/completions"
            body = {
                "model": self.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "temperature": 0,
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False


def load_role_prompt(role: str, roles_dir: str = "roles") -> str:
    """Load a role's system prompt from roles/<role>.md."""
    path = os.path.join(roles_dir, f"{role}.md")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Role prompt not found: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()

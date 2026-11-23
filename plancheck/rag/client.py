"""The language-model client used for explanations.

``LLMClient`` is the whole interface: a system prompt and a user message in, text out.
``OpenRouterClient`` calls OpenRouter's chat-completions endpoint over HTTPS with the
standard library, as the Census geocoder client does, so it adds no dependency.

The API key is read from the ``OPENROUTER_API_KEY`` environment variable, or from the
``.env`` file at the repository root. It is sent only in the request's Authorization
header and never appears in an error message, a log line or a saved file.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

import truststore

from plancheck.config import load_config

KEY_NAME = "OPENROUTER_API_KEY"
_REPO_ROOT = Path(__file__).resolve().parents[2]


class LLMError(RuntimeError):
    """The language-model service could not be used or returned no text."""


class LLMClient(Protocol):
    """Anything that turns a system prompt and a user message into text."""

    service: str
    model_id: str

    def complete(self, system: str, user: str) -> str: ...


def load_api_key(env_file: Path | None = None) -> str | None:
    """The key from the environment, else from ``.env``. None when neither has one."""
    value = os.environ.get(KEY_NAME, "").strip()
    if value:
        return value
    path = env_file or _REPO_ROOT / ".env"
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, rest = line.strip().partition("=")
        if separator and name.strip() == KEY_NAME:
            return rest.strip().strip("\"'") or None
    return None


class OpenRouterClient:
    """Sends one chat-completions request per call. Temperature is zero."""

    def __init__(
        self,
        api_key: str,
        model_id: str,
        *,
        service: str,
        base_url: str,
        timeout_s: float = 60.0,
        max_output_tokens: int = 2000,
        reasoning: bool = True,
    ) -> None:
        self.service = service
        self.model_id = model_id
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._timeout_s = timeout_s
        self._max_output_tokens = max_output_tokens
        self._reasoning = reasoning
        # Use the operating system's certificate store.
        self._tls = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    def complete(self, system: str, user: str) -> str:
        body: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": self._max_output_tokens,
        }
        if not self._reasoning:
            # Reasoning tokens count against max_tokens on reasoning models, and a short
            # templated answer does not need them.
            body["reasoning"] = {"enabled": False}
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "X-Title": "PlanCheck",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_s, context=self._tls
            ) as reply:
                data: Any = json.load(reply)
        except urllib.error.HTTPError as error:
            raise LLMError(
                f"{self.service} returned HTTP {error.code}: {_message(error)}"
            ) from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise LLMError(f"{self.service} could not be reached: {type(error).__name__}") from None
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            detail = data.get("error", {}).get("message") if isinstance(data, dict) else None
            raise LLMError(
                f"{self.service} returned no text: {detail or 'unexpected reply'}"
            ) from None
        if not isinstance(text, str) or not text.strip():
            limit = choice.get("finish_reason") == "length" if isinstance(choice, dict) else False
            hint = " (its output limit was reached before any text)" if limit else ""
            raise LLMError(f"{self.service} returned no text{hint}")
        return text.strip()


def _message(error: urllib.error.HTTPError) -> str:
    """The service's own error text, shortened. The request, and so the key, is not echoed."""
    try:
        data = json.loads(error.read().decode("utf-8", "replace"))
        return str(data["error"]["message"])[:200]
    except (ValueError, KeyError, TypeError):
        return str(error.reason)[:200]


def explainer_status() -> dict[str, object]:
    """What the page needs to label the explain action. The key itself is never included."""
    config = load_config("explain")
    return {
        "available": load_api_key() is not None,
        "service": str(config["service"]),
        "model": str(config["model"]),
        "key_name": KEY_NAME,
    }


def default_client() -> OpenRouterClient:
    """The client described by ``configs/explain.yaml``. Raises when no key is configured."""
    config = load_config("explain")
    key = load_api_key()
    if key is None:
        raise LLMError(f"Explanations are off: set {KEY_NAME} in the environment or in .env")
    return OpenRouterClient(
        key,
        str(config["model"]),
        service=str(config["service"]),
        base_url=str(config["base_url"]),
        timeout_s=float(config["timeout_s"]),
        max_output_tokens=int(config["max_output_tokens"]),
        reasoning=bool(config.get("reasoning", True)),
    )

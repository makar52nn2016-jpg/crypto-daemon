"""
trudyagi/core/zai_client.py — Z.ai GLM backend (FREE — uses z-ai CLI via subprocess)

This is the recommended backend for Trudyagi because:
  1. It's FREE (Z.ai's in-house GLM model, no API costs)
  2. Already configured locally via /etc/.z-ai-config (auto-distributed in the env)
  3. Supports system prompts via `--system` flag
  4. Returns OpenAI-compatible JSON output

Required: z-ai CLI installed (npm install -g z-ai-web-dev-sdk OR local node_modules)

Setup on GitHub Actions:
  - npm install z-ai-web-dev-sdk (installs z-ai CLI)
  - Copy /etc/.z-ai-config from secret Z_AI_CONFIG (JSON with baseUrl/apiKey/token/etc)

Usage in Trudyagi:
  - In .env: LLM_BACKEND=zai (overrides OpenAI-compatible client)
  - No LLM_API_KEY needed (uses /etc/.z-ai-config)
"""

import json
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional


class ZaiLLMClient:
    """LLM client that calls `z-ai chat` CLI via subprocess.

    Zero-cost: uses Z.ai's free GLM-4-Plus endpoint via /etc/.z-ai-config.
    """

    def __init__(self, *args, **kwargs):
        # Find z-ai CLI binary
        self.z_ai_bin = shutil.which("z-ai")
        if not self.z_ai_bin:
            # Try local node_modules
            local_bin = Path("/home/z/my-project/node_modules/.bin/z-ai")
            if local_bin.exists():
                self.z_ai_bin = str(local_bin)
        if not self.z_ai_bin:
            raise RuntimeError(
                "z-ai CLI not found. Install with: npm install z-ai-web-dev-sdk"
            )

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send chat completion request via z-ai CLI.

        Returns just the assistant message content (not the full JSON response).
        """
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            output_path = tmp.name

        try:
            cmd = [
                self.z_ai_bin,
                "chat",
                "-p", user_prompt,
                "-s", system_prompt,
                "-o", output_path,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"z-ai CLI failed (exit {result.returncode}): "
                    f"{result.stderr[:300]}"
                )

            with open(output_path, encoding="utf-8") as f:
                response = json.load(f)

            return response["choices"][0]["message"]["content"]
        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    def is_alive(self) -> bool:
        """Quick health check — send a 1-token 'ping'."""
        try:
            response = self.chat(
                system_prompt="Reply with exactly 'pong'.",
                user_prompt="ping",
            )
            return bool(response and len(response) > 0)
        except Exception:
            return False

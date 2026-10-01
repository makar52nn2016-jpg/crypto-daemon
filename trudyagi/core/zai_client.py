"""
trudyagi/core/zai_client.py — Z.ai GLM backend (FREE — uses z-ai CLI via subprocess)

This is the recommended backend for Trudyagi because:
  1. It's FREE (Z.ai's in-house GLM model, no API costs)
  2. Already configured locally via /etc/.z-ai-config (auto-distributed in the env)
  3. Supports system prompts via `--system` flag
  4. Returns OpenAI-compatible JSON output

Required: z-ai-web-dev-sdk npm package + node.js (>=20) OR bun runtime

Setup on GitHub Actions:
  - npm install z-ai-web-dev-sdk (installs z-ai CLI source)
  - node.js provided by actions/setup-node
  - Copy .z-ai-config from secret Z_AI_CONFIG (JSON with baseUrl/apiKey/token/etc)

Note: z-ai CLI's shebang is `#!/usr/bin/env bun` but it ALSO runs under `node` —
we detect both and use whichever is available. This avoids needing bun on GHA.

Usage in Trudyagi:
  - In .env: LLM_BACKEND=zai (overrides OpenAI-compatible client)
  - No LLM_API_KEY needed (uses .z-ai-config file)
"""

import json
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional


def _find_z_ai_invocation():
    """Find how to invoke z-ai CLI.

    Returns a list (argv) suitable for subprocess.run.
    Tries, in order:
      1. `z-ai` if on PATH (assumes bun runtime is available)
      2. `bun /path/to/z-ai-web-dev-sdk/dist/cli.js` (if bun available)
      3. `node /path/to/z-ai-web-dev-sdk/dist/cli.js` (universal fallback)

    Returns None if z-ai SDK is not installed anywhere.
    """
    # Try direct `z-ai` binary first (local dev with bun installed)
    if shutil.which("z-ai"):
        # Quick check: does it actually run?
        try:
            result = subprocess.run(
                ["z-ai", "--help"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return ["z-ai"]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Find the SDK's cli.js — check common locations
    cli_js_paths = [
        # 1. Project's local node_modules (cwd-relative)
        Path.cwd() / "node_modules" / "z-ai-web-dev-sdk" / "dist" / "cli.js",
        # 2. Project root node_modules (when running from trudyagi/ subdir)
        Path.cwd().parent / "node_modules" / "z-ai-web-dev-sdk" / "dist" / "cli.js",
        # 3. Home dir projects
        Path.home() / "my-project" / "node_modules" / "z-ai-web-dev-sdk" / "dist" / "cli.js",
        # 4. Global node_modules (npm install -g)
        Path("/usr/local/lib/node_modules/z-ai-web-dev-sdk/dist/cli.js"),
        Path("/usr/lib/node_modules/z-ai-web-dev-sdk/dist/cli.js"),
    ]

    cli_js = None
    for path in cli_js_paths:
        if path.exists():
            cli_js = path
            break

    if not cli_js:
        # Search PATH for any z-ai-web-dev-sdk
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(path_dir).parent / "node_modules" / "z-ai-web-dev-sdk" / "dist" / "cli.js"
            if candidate.exists():
                cli_js = candidate
                break
            # Also check `lib` subdirectory
            candidate2 = Path(path_dir).parent / "lib" / "node_modules" / "z-ai-web-dev-sdk" / "dist" / "cli.js"
            if candidate2.exists():
                cli_js = candidate2
                break

    if not cli_js:
        return None

    # Try `bun` first (faster), then `node` (universal)
    for runtime in ("bun", "node"):
        if shutil.which(runtime):
            return [runtime, str(cli_js)]

    return None


class ZaiLLMClient:
    """LLM client that calls `z-ai chat` CLI via subprocess.

    Zero-cost: uses Z.ai's free GLM-4-Plus endpoint via .z-ai-config.
    """

    def __init__(self, *args, **kwargs):
        self.invocation = _find_z_ai_invocation()
        if not self.invocation:
            raise RuntimeError(
                "z-ai CLI not found. Install with: npm install z-ai-web-dev-sdk "
                "(needs bun or node >=20 runtime)"
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
            cmd = self.invocation + [
                "chat",
                "-p", user_prompt,
                "-s", system_prompt,
                "-o", output_path,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 min max — GLM can be slow on complex prompts
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

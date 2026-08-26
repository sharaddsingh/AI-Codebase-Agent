"""Backend configuration.

All configuration comes from environment variables (or a local ``.env`` file),
never from the frontend. Secrets like ``ANTHROPIC_API_KEY`` live here and are only
ever read server-side.
"""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.budget import Budget


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # -- model provider ---------------------------------------------------
    model_provider: str = "anthropic"        # "anthropic" | "mock"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    anthropic_base_url: str | None = None
    anthropic_max_tokens: int = 4096
    agent_temperature: float = 0.0

    # -- agent budgets ----------------------------------------------------
    # Defaults mirror agent.budget.Budget and are sized for real repositories;
    # override per-deployment via AGENT_MAX_* env vars. Tool calls are the
    # intended binding limit (steps kept above it).
    agent_max_tool_calls: int = 20
    agent_max_seconds: float = 150.0
    agent_max_files: int = 20
    agent_max_context_bytes: int = 300_000
    agent_max_steps: int = 24

    # -- repository access ------------------------------------------------
    # os.pathsep-separated allow-list. Empty => unrestricted (dev convenience);
    # a warning is logged at startup when unrestricted.
    allowed_repo_roots: str = ""
    respect_gitignore: bool = True
    # Optional path auto-registered at startup (handy for demos, e.g. the fixture).
    default_repo_path: str = ""

    # -- GitHub access via the official GitHub MCP server (read-only) -----
    # GitHub repositories are investigated through the official GitHub MCP
    # server over remote Streamable HTTP, authenticated by a server-side PAT.
    # A token is REQUIRED for GitHub repos (the remote server mandates one even
    # for public repositories). It is read only here and is never sent to the
    # frontend, a response, a citation, a log, or an error message.
    github_token: str | None = None
    github_mcp_url: str = "https://api.githubcopilot.com/mcp/readonly"
    github_mcp_toolsets: str = "repos,git"
    github_mcp_timeout: float = 30.0

    # -- server -----------------------------------------------------------
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # -- derived helpers --------------------------------------------------
    @property
    def model_configured(self) -> bool:
        """True if the agent can actually talk to a model."""
        if self.model_provider == "mock":
            return True
        return bool(self.anthropic_api_key)

    def allowed_roots_list(self) -> list[str] | None:
        raw = self.allowed_repo_roots.strip()
        if not raw:
            return None
        return [
            os.path.realpath(os.path.expanduser(p))
            for p in raw.split(os.pathsep)
            if p.strip()
        ]

    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def budget(self) -> Budget:
        return Budget(
            max_tool_calls=self.agent_max_tool_calls,
            max_seconds=self.agent_max_seconds,
            max_files_read=self.agent_max_files,
            max_context_bytes=self.agent_max_context_bytes,
            max_steps=self.agent_max_steps,
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

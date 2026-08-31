"""Backend configuration.

All configuration comes from environment variables (or a local ``.env`` file),
never from the frontend. Secrets like ``ANTHROPIC_API_KEY`` live here and are only
ever read server-side.
"""

from __future__ import annotations

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

    # -- upload (browser-supplied folders) --------------------------------
    # Where the upload pipeline writes files. The directory is created on
    # first upload and contains one subdirectory per uploaded repo. Cleaning
    # up an uploaded repo also wipes its subdirectory here.
    #
    # Uploads registered here are re-registered on startup (deps.rehydrate_uploads)
    # so a restart — a code edit under --reload, a redeploy — does not leave the
    # frontend holding ids the backend has forgotten.
    upload_root: str = "./uploaded_repos"

    # Caps for a single upload; see backend.uploaded_repos.UploadLimits.
    # File count is the limit real projects hit, so it is generous. Total bytes
    # is the memory guard (the multipart parser buffers parts before they are
    # written), so raise it only on a host with the RAM to match.
    upload_max_files: int = 20_000
    upload_max_file_mb: int = 10
    upload_max_total_mb: int = 100

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

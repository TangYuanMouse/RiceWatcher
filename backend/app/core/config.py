import json
import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "RiceWatcher Gateway"
    version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]
    email_skill_dir: str = ""
    email_skill_node_command: str = "node"
    email_tool_timeout_seconds: int = 45
    database_path: str = ""
    scheduler_poll_seconds: int = 5
    default_email_job_interval_seconds: int = 300
    email_classification_confidence_threshold: float = 0.75
    email_extraction_confidence_threshold: float = 0.72


class LLMProviderConfig(BaseModel):
    provider: str = "openai-compatible"
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""
    timeout_seconds: int = 60
    enabled: bool = False


def _default_llm_config_path() -> Path:
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / "config" / "llm_provider.json"


def _default_email_skill_dir() -> Path:
    workspace_root = Path(__file__).resolve().parents[3]
    return workspace_root / "imap-smtp-email"


def _default_database_path() -> Path:
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / "data" / "ricewatcher.db"


def _resolve_llm_config_path() -> Path:
    env_path = os.getenv("LLM_PROVIDER_CONFIG")
    if env_path:
        return Path(env_path)

    backend_root = Path(__file__).resolve().parents[2]
    local_path = backend_root / "config" / "llm_provider.local.json"
    if local_path.exists():
        return local_path

    return _default_llm_config_path()


def load_llm_provider_config() -> LLMProviderConfig:
    config_path = _resolve_llm_config_path()

    file_data: dict[str, object] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            file_data = json.load(f)

    # Environment variables override file values.
    provider = os.getenv("LLM_PROVIDER", str(file_data.get("provider", "openai-compatible")))
    base_url = os.getenv("LLM_BASE_URL", str(file_data.get("base_url", "")))
    api_key = os.getenv("LLM_API_KEY", str(file_data.get("api_key", "")))
    model_name = os.getenv("LLM_MODEL_NAME", str(file_data.get("model_name", "")))
    timeout_seconds = int(os.getenv("LLM_TIMEOUT_SECONDS", str(file_data.get("timeout_seconds", 60))))
    enabled_text = os.getenv("LLM_ENABLED", str(file_data.get("enabled", False))).lower()
    enabled = enabled_text in {"1", "true", "yes", "on"}

    return LLMProviderConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        timeout_seconds=timeout_seconds,
        enabled=enabled,
    )


settings = Settings()
llm_provider_config = load_llm_provider_config()

settings.email_skill_dir = os.getenv("EMAIL_SKILL_DIR", str(_default_email_skill_dir()))
settings.email_skill_node_command = os.getenv("EMAIL_SKILL_NODE", "node")
settings.email_tool_timeout_seconds = int(os.getenv("EMAIL_TOOL_TIMEOUT_SECONDS", "45"))
settings.database_path = os.getenv("DATABASE_PATH", str(_default_database_path()))
settings.scheduler_poll_seconds = int(os.getenv("SCHEDULER_POLL_SECONDS", "5"))
settings.default_email_job_interval_seconds = int(
    os.getenv("DEFAULT_EMAIL_JOB_INTERVAL_SECONDS", "300")
)
settings.email_classification_confidence_threshold = float(
    os.getenv("EMAIL_CLASSIFICATION_CONFIDENCE_THRESHOLD", "0.75")
)
settings.email_extraction_confidence_threshold = float(
    os.getenv("EMAIL_EXTRACTION_CONFIDENCE_THRESHOLD", "0.72")
)

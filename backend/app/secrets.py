from __future__ import annotations

import json
import os
import secrets as py_secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .aws import boto3_client
from .config import AppSettings
from .retries import retry_transient


class SecretProviderError(RuntimeError):
    """Raised when a required secret cannot be loaded."""


DEFAULT_TOOL_EXECUTION_MODE = "local"
DEFAULT_MCP_SERVER_URL = "http://host.docker.internal:9000/sse"
DEFAULT_MCP_PROJECT_ID = "dstrmaysam-healthcare-knowledge-multi-agent"
DEFAULT_MCP_TOOL_TIMEOUT_SECONDS = 30
DEFAULT_MCP_TOOL_FALLBACK_TO_LOCAL = False


@dataclass(frozen=True)
class AppSecrets:
    session_secret: str
    auth_users: dict[str, str]
    user_profiles: dict[str, dict[str, Any]]
    guardian_api_key: str = ""


@dataclass(frozen=True)
class AzureOpenAISecrets:
    endpoint: str
    api_key: str
    api_version: str
    chat_deployment: str
    fast_chat_deployment: str
    embedding_deployment: str


@dataclass(frozen=True)
class LangfuseSecrets:
    public_key: str
    secret_key: str
    base_url: str


@dataclass(frozen=True)
class ToolExecutionSecrets:
    tool_execution_mode: str
    mcp_server_url: str
    mcp_project_id: str
    mcp_tool_timeout_seconds: int
    mcp_tool_fallback_to_local: bool


@dataclass(frozen=True)
class TwilioWhatsAppSecrets:
    enabled: bool
    auth_token: str
    account_sid: str
    from_number: str
    webhook_public_url: str
    async_enabled: bool
    allow_unmapped_users: bool
    default_roles: tuple[str, ...]
    default_departments: tuple[str, ...]
    users: dict[str, dict[str, Any]]
    max_reply_chars: int


def _secret_value(data: dict[str, Any], key: str, default: Any = "") -> Any:
    if key in data:
        return data.get(key)
    upper_key = key.upper()
    if upper_key in data:
        return data.get(upper_key)
    return default


def _secret_first(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = _secret_value(data, key, None)
        if value not in (None, ""):
            return value
    return default


def _secret_bool(data: dict[str, Any], key: str, default: bool = False) -> bool:
    value = _secret_value(data, key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _secret_int(data: dict[str, Any], key: str, default: int) -> int:
    value = _secret_value(data, key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _secret_csv_tuple(data: dict[str, Any], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = _secret_value(data, key, list(default))
    if isinstance(value, str):
        return tuple(item.strip().lower() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip().lower() for item in value if str(item).strip())
    return default


def _secret_mapping(data: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    value = _secret_value(data, key, {})
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        value = parsed
    if not isinstance(value, dict):
        return {}
    return {str(k): dict(v) for k, v in value.items() if isinstance(v, dict)}


class SecretProvider:
    """Loads application secrets from AWS Secrets Manager.

    The application intentionally does not read secret values from environment
    variables. Environment variables contain only secret names and non-sensitive
    configuration.
    """

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._cache: dict[str, dict[str, Any]] = {}

    def invalidate(self, secret_name: str | None = None) -> None:
        if secret_name is None:
            self._cache.clear()
            return
        self._cache.pop(secret_name, None)

    @retry_transient
    def get_json(self, secret_name: str) -> dict[str, Any]:
        if secret_name in self._cache:
            return self._cache[secret_name]

        try:
            import boto3
        except ImportError as exc:
            raise SecretProviderError(
                "boto3 is required to load secrets from AWS Secrets Manager"
            ) from exc

        client = boto3_client(self.settings, "secretsmanager")
        try:
            response = client.get_secret_value(SecretId=secret_name)
        except Exception as exc:  # boto3 raises service-specific exceptions.
            raise SecretProviderError(f"Unable to load secret {secret_name!r}") from exc

        raw = response.get("SecretString")
        if not raw:
            raise SecretProviderError(f"Secret {secret_name!r} does not contain SecretString JSON")

        try:
            value = json.loads(raw.lstrip("\ufeffï»¿"))
        except json.JSONDecodeError as exc:
            raise SecretProviderError(f"Secret {secret_name!r} is not valid JSON") from exc

        if not isinstance(value, dict):
            raise SecretProviderError(f"Secret {secret_name!r} must contain a JSON object")

        self._cache[secret_name] = value
        return value

    @retry_transient
    def put_json(self, secret_name: str, value: dict[str, Any]) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise SecretProviderError(
                "boto3 is required to write secrets to AWS Secrets Manager"
            ) from exc

        client = boto3_client(self.settings, "secretsmanager")
        try:
            client.put_secret_value(SecretId=secret_name, SecretString=json.dumps(value))
        except Exception as exc:  # boto3 raises service-specific exceptions.
            raise SecretProviderError(f"Unable to update secret {secret_name!r}") from exc
        self._cache[secret_name] = dict(value)

    def load_app(self) -> AppSecrets:
        data = self.get_json(self.settings.app_secret_name)
        session_secret = str(data.get("session_secret", ""))
        auth_users = data.get("auth_users", {})
        user_profiles = data.get("user_profiles", {})
        if not session_secret:
            raise SecretProviderError("App secret must contain session_secret")
        if not isinstance(auth_users, dict) or not auth_users:
            raise SecretProviderError("App secret must contain non-empty auth_users map")
        if not isinstance(user_profiles, dict):
            raise SecretProviderError("App secret user_profiles must be a JSON object when provided")
        return AppSecrets(
            session_secret=session_secret,
            auth_users={str(username): str(password_hash) for username, password_hash in auth_users.items()},
            user_profiles={
                str(username): dict(profile) for username, profile in user_profiles.items() if isinstance(profile, dict)
            },
            guardian_api_key=str(data.get("guardian_api_key") or ""),
        )

    def load_azure_openai(self) -> AzureOpenAISecrets:
        data = self.get_json(self.settings.azure_openai_secret_name)
        endpoint = str(_secret_first(data, "endpoint", "AZURE_OPENAI_ENDPOINT")).strip()
        api_key = str(_secret_first(data, "api_key", "AZURE_OPENAI_API_KEY")).strip()
        api_version = str(
            _secret_first(data, "api_version", "AZURE_OPENAI_API_VERSION", default="2025-04-01-preview")
        ).strip()
        embedding_deployment = str(
            _secret_first(data, "embedding_deployment", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        ).strip()
        chat_deployment = (
            self.settings.azure_openai_deployment
            or str(_secret_first(data, "chat_deployment", "AZURE_OPENAI_DEPLOYMENT")).strip()
        )
        fast_chat_deployment = (
            self.settings.azure_openai_fast_deployment
            or str(_secret_first(data, "fast_chat_deployment", "AZURE_OPENAI_FAST_DEPLOYMENT")).strip()
            or chat_deployment
        )
        missing = []
        if not endpoint:
            missing.append("endpoint or AZURE_OPENAI_ENDPOINT")
        if not api_key:
            missing.append("api_key or AZURE_OPENAI_API_KEY")
        if not embedding_deployment:
            missing.append("embedding_deployment or AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        if not chat_deployment:
            missing.append("chat_deployment or AZURE_OPENAI_DEPLOYMENT")
        if missing:
            raise SecretProviderError(
                f"Azure OpenAI secret is missing required keys: {', '.join(missing)}"
            )
        return AzureOpenAISecrets(
            endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            chat_deployment=chat_deployment,
            fast_chat_deployment=fast_chat_deployment,
            embedding_deployment=embedding_deployment,
        )

    def load_langfuse(self) -> LangfuseSecrets:
        data = self.get_json(self.settings.langfuse_secret_name)
        required = ["public_key", "secret_key", "base_url"]
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise SecretProviderError(f"Langfuse secret is missing required keys: {', '.join(missing)}")
        return LangfuseSecrets(
            public_key=str(data["public_key"]),
            secret_key=str(data["secret_key"]),
            base_url=str(data["base_url"]),
        )

    def load_tool_execution(self) -> ToolExecutionSecrets:
        data = self.get_json(self.settings.app_secret_name)
        return ToolExecutionSecrets(
            tool_execution_mode=str(
                _secret_value(data, "tool_execution_mode", DEFAULT_TOOL_EXECUTION_MODE)
            ).strip().lower(),
            mcp_server_url=str(_secret_value(data, "mcp_server_url", DEFAULT_MCP_SERVER_URL)),
            mcp_project_id=str(_secret_value(data, "mcp_project_id", DEFAULT_MCP_PROJECT_ID)),
            mcp_tool_timeout_seconds=_secret_int(
                data,
                "mcp_tool_timeout_seconds",
                DEFAULT_MCP_TOOL_TIMEOUT_SECONDS,
            ),
            mcp_tool_fallback_to_local=_secret_bool(
                data,
                "mcp_tool_fallback_to_local",
                DEFAULT_MCP_TOOL_FALLBACK_TO_LOCAL,
            ),
        )

    def load_twilio_whatsapp(self) -> TwilioWhatsAppSecrets:
        data = self.get_json(self.settings.app_secret_name)
        return TwilioWhatsAppSecrets(
            enabled=_secret_bool(data, "twilio_whatsapp_enabled", False),
            auth_token=str(_secret_value(data, "twilio_auth_token", "")),
            account_sid=str(_secret_value(data, "twilio_account_sid", "")),
            from_number=str(_secret_value(data, "twilio_whatsapp_from", "")),
            webhook_public_url=str(_secret_value(data, "twilio_whatsapp_webhook_url", "")),
            async_enabled=_secret_bool(data, "twilio_whatsapp_async_enabled", False),
            allow_unmapped_users=_secret_bool(data, "twilio_whatsapp_allow_unmapped", False),
            default_roles=_secret_csv_tuple(data, "twilio_whatsapp_default_roles", ("staff",)),
            default_departments=_secret_csv_tuple(data, "twilio_whatsapp_default_departments", ()),
            users=_secret_mapping(data, "twilio_whatsapp_users"),
            max_reply_chars=_secret_int(data, "twilio_whatsapp_max_reply_chars", 1400),
        )


class StaticSecretProvider(SecretProvider):
    """Test-only provider that keeps the deployed app contract intact."""

    def __init__(self, settings: AppSettings, secrets: dict[str, dict[str, Any]]):
        super().__init__(settings)
        self._static_secrets = secrets

    def get_json(self, secret_name: str) -> dict[str, Any]:
        if secret_name not in self._static_secrets:
            raise SecretProviderError(f"Static secret {secret_name!r} not configured")
        return self._static_secrets[secret_name]

    def put_json(self, secret_name: str, value: dict[str, Any]) -> None:
        self._static_secrets[secret_name] = dict(value)
        self._cache[secret_name] = dict(value)


class EnvSecretProvider(SecretProvider):
    """Local-mode provider backed by environment variables and a JSON app secret file."""

    def get_json(self, secret_name: str) -> dict[str, Any]:
        if secret_name == self.settings.app_secret_name:
            return self._load_local_app_secret()
        if secret_name == self.settings.azure_openai_secret_name:
            return self._azure_secret_from_env()
        if secret_name == self.settings.langfuse_secret_name:
            return self._langfuse_secret_from_env()
        raise SecretProviderError(f"Local secret {secret_name!r} is not configured")

    def put_json(self, secret_name: str, value: dict[str, Any]) -> None:
        if secret_name != self.settings.app_secret_name:
            raise SecretProviderError("Only the local app secret can be updated in local mode")
        path = Path(self.settings.local_app_secret_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        self._cache[secret_name] = dict(value)

    def _load_local_app_secret(self) -> dict[str, Any]:
        if self.settings.app_secret_name in self._cache:
            return self._cache[self.settings.app_secret_name]
        path = Path(self.settings.local_app_secret_file)
        if path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SecretProviderError(f"Local app secret {str(path)!r} is not valid JSON") from exc
            if not isinstance(value, dict):
                raise SecretProviderError(f"Local app secret {str(path)!r} must contain a JSON object")
        else:
            value = self._default_local_app_secret()
            self.put_json(self.settings.app_secret_name, value)
        self._cache[self.settings.app_secret_name] = value
        return value

    def _default_local_app_secret(self) -> dict[str, Any]:
        from .auth import hash_password

        username = self.settings.local_test_admin_username.strip() or "admin"
        password = self.settings.local_test_admin_password or "admin123"
        session_secret = os.getenv("LOCAL_SESSION_SECRET") or py_secrets.token_urlsafe(32)
        return {
            "session_secret": session_secret,
            "auth_users": {username: hash_password(password, iterations=1000)},
            "user_profiles": {
                username: {
                    "roles": [
                        "admin",
                        "doctor",
                        "nurse",
                        "pharmacy",
                        "clinical_governance",
                        "manager",
                        "staff",
                    ],
                    "departments": ["clinical_governance", "operations", "it", "hr", "finance"],
                    "password_change_required": False,
                }
            },
        }

    def load_twilio_whatsapp(self) -> TwilioWhatsAppSecrets:
        def env_bool(name: str, default: bool = False) -> bool:
            return os.getenv(name, "true" if default else "false").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        raw_users = os.getenv("TWILIO_WHATSAPP_USERS", "{}")
        try:
            users_value = json.loads(raw_users) if raw_users.strip() else {}
        except json.JSONDecodeError:
            users_value = {}
        if not isinstance(users_value, dict):
            users_value = {}
        return TwilioWhatsAppSecrets(
            enabled=env_bool("TWILIO_WHATSAPP_ENABLED", False),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            from_number=os.getenv("TWILIO_WHATSAPP_FROM", ""),
            webhook_public_url=os.getenv("TWILIO_WHATSAPP_WEBHOOK_URL", ""),
            async_enabled=env_bool("TWILIO_WHATSAPP_ASYNC_ENABLED", False),
            allow_unmapped_users=env_bool("TWILIO_WHATSAPP_ALLOW_UNMAPPED", False),
            default_roles=tuple(
                role.strip().lower()
                for role in os.getenv("TWILIO_WHATSAPP_DEFAULT_ROLES", "staff").split(",")
                if role.strip()
            ),
            default_departments=tuple(
                department.strip().lower()
                for department in os.getenv("TWILIO_WHATSAPP_DEFAULT_DEPARTMENTS", "").split(",")
                if department.strip()
            ),
            users={str(k): dict(v) for k, v in users_value.items() if isinstance(v, dict)},
            max_reply_chars=int(os.getenv("TWILIO_WHATSAPP_MAX_REPLY_CHARS", "1400")),
        )

    def _azure_secret_from_env(self) -> dict[str, Any]:
        chat_deployment = self.settings.azure_openai_deployment or os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
        fast_chat_deployment = (
            self.settings.azure_openai_fast_deployment
            or os.getenv("AZURE_OPENAI_FAST_DEPLOYMENT", "")
            or chat_deployment
        )
        return {
            "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            "api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
            "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
            "chat_deployment": chat_deployment,
            "fast_chat_deployment": fast_chat_deployment,
            "embedding_deployment": os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", ""),
        }

    def _langfuse_secret_from_env(self) -> dict[str, Any]:
        return {
            "public_key": os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            "secret_key": os.getenv("LANGFUSE_SECRET_KEY", ""),
            "base_url": os.getenv("LANGFUSE_BASE_URL", ""),
        }

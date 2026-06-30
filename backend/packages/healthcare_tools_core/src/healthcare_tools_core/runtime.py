from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class AppSettingsLike(Protocol):
    deterministic_lookup_enabled: bool
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_sslmode: str
    local_data_dir: str


@dataclass(frozen=True)
class HealthcareUserContext:
    user_id: str = "mcp-user"
    roles: tuple[str, ...] = ("staff",)
    departments: tuple[str, ...] = ()
    password_change_required: bool = False

    def has_role(self, role: str) -> bool:
        return role.lower() in self.roles


def user_context_from_payload(payload: dict[str, Any] | None) -> HealthcareUserContext:
    payload = payload or {}
    roles = payload.get("roles") or ["staff"]
    departments = payload.get("departments") or []
    return HealthcareUserContext(
        user_id=str(payload.get("user_id") or payload.get("sub") or "mcp-user"),
        roles=tuple(str(role).lower() for role in roles),
        departments=tuple(str(department).lower() for department in departments),
        password_change_required=bool(payload.get("password_change_required", False)),
    )

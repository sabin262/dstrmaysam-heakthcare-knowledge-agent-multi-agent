from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import escape
from typing import Any

from fastapi import HTTPException, Request, status

from .healthcare import HealthcareUserContext
from .secrets import TwilioWhatsAppSecrets


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TwilioInboundMessage:
    from_address: str
    to_address: str
    body: str
    message_sid: str
    profile_name: str = ""
    wa_id: str = ""


def twiml_message(body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(body)}</Message></Response>'


def normalize_whatsapp_address(value: str) -> str:
    raw = str(value or "").strip()
    if raw.lower().startswith("whatsapp:"):
        raw = raw.split(":", 1)[1]
    raw = raw.replace(" ", "")
    if raw.startswith("+"):
        return "+" + re.sub(r"\D", "", raw)
    digits = re.sub(r"\D", "", raw)
    return f"+{digits}" if digits else ""


def _mapping_keys(address: str, wa_id: str = "") -> list[str]:
    normalized = normalize_whatsapp_address(address)
    keys = []
    if normalized:
        keys.extend([normalized, f"whatsapp:{normalized}", normalized.lstrip("+")])
    if wa_id:
        wa_digits = re.sub(r"\D", "", str(wa_id))
        keys.extend([str(wa_id), f"+{wa_digits}" if wa_digits else ""])
    return list(dict.fromkeys(key for key in keys if key))


def user_context_for_sender(config: TwilioWhatsAppSecrets, sender: str, wa_id: str = "") -> HealthcareUserContext | None:
    profile: dict[str, Any] | None = None
    for key in _mapping_keys(sender, wa_id):
        candidate = config.users.get(key)
        if candidate is not None:
            profile = candidate
            break
    if profile is None:
        if not config.allow_unmapped_users:
            return None
        normalized = normalize_whatsapp_address(sender) or str(wa_id or "unknown")
        return HealthcareUserContext(
            user_id=f"whatsapp:{normalized}",
            roles=tuple(role.lower() for role in config.default_roles) or ("staff",),
            departments=tuple(department.lower() for department in config.default_departments),
        )
    if profile.get("enabled") is False:
        return None
    roles = profile.get("roles") or config.default_roles or ("staff",)
    departments = profile.get("departments") or config.default_departments or ()
    user_id = str(profile.get("user_id") or profile.get("username") or normalize_whatsapp_address(sender))
    return HealthcareUserContext(
        user_id=user_id,
        roles=tuple(str(role).lower() for role in roles),
        departments=tuple(str(department).lower() for department in departments),
        password_change_required=False,
    )


async def parse_twilio_message(request: Request) -> tuple[TwilioInboundMessage, dict[str, str]]:
    form = await request.form()
    params = {str(key): str(value) for key, value in form.items()}
    message = TwilioInboundMessage(
        from_address=params.get("From", ""),
        to_address=params.get("To", ""),
        body=params.get("Body", "").strip(),
        message_sid=params.get("MessageSid", ""),
        profile_name=params.get("ProfileName", ""),
        wa_id=params.get("WaId", ""),
    )
    return message, params


def validate_twilio_signature(
    *,
    request: Request,
    params: dict[str, str],
    auth_token: str,
    public_url_override: str = "",
) -> bool:
    if not auth_token:
        return False
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False
    url = public_url_override.strip() or str(request.url)
    signed = url + "".join(f"{key}{value}" for key, value in sorted(params.items()))
    expected = base64.b64encode(
        hmac.new(auth_token.encode("utf-8"), signed.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")
    return hmac.compare_digest(expected, signature)


def require_valid_twilio_request(
    *,
    request: Request,
    params: dict[str, str],
    config: TwilioWhatsAppSecrets,
) -> None:
    if validate_twilio_signature(
        request=request,
        params=params,
        auth_token=config.auth_token,
        public_url_override=config.webhook_public_url,
    ):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")


def format_whatsapp_answer(answer: str, *, max_chars: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", str(answer or "").strip())
    if not text:
        return "I could not generate an answer for that request."
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 80)].rstrip() + "\n\nReply in the web chat for the full detailed answer."


def split_whatsapp_messages(text: str, *, max_chars: int) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n\n", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = remaining.rfind("\n", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = remaining.rfind(" ", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = max_chars
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return [chunk for chunk in chunks if chunk]


def send_twilio_whatsapp_message(
    *,
    config: TwilioWhatsAppSecrets,
    to_address: str,
    body: str,
) -> None:
    if not config.account_sid or not config.auth_token or not config.from_number:
        raise RuntimeError("Twilio outbound credentials are not configured")
    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{config.account_sid}/Messages.json"
    payload = urllib.parse.urlencode(
        {
            "To": to_address,
            "From": config.from_number,
            "Body": body,
        }
    ).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, method="POST")
    token = base64.b64encode(f"{config.account_sid}:{config.auth_token}".encode("utf-8")).decode("ascii")
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status >= 400:
            raise RuntimeError(f"Twilio message send failed with HTTP {response.status}")

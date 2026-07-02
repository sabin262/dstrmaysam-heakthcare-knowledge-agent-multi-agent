import json
import os
import html
import queue
import re
import textwrap
import threading
from typing import Any
from urllib.parse import quote

import requests
import streamlit as st
import streamlit.components.v1 as components


APP_TITLE = "⚕️ Healthcare Knowledge Agent"
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
KNOWN_ROLES = ["admin", "staff", "doctor", "nurse", "pharmacy", "clinical_governance", "manager"]
MIN_PASSWORD_LENGTH = 8
AUTH_COOKIE_NAME = "hka_access_token"
AUTH_COOKIE_DEFAULT_MAX_AGE_SECONDS = 3600
NEWS_REFRESH_SECONDS = 1800
CHAT_PROGRESS_MESSAGES = [
    "Reviewing the question and choosing the right data source.",
    "Checking structured lookup data and indexed documents if needed.",
    "Preparing a concise answer.",
]
MCP_SERVER_URL_OPTIONS = [
    (
        "Shared MCP Server",
        "http://internal-dstrmaysam-shared-mcp-alb-748190876.eu-west-2.elb.amazonaws.com/sse",
    ),
    (
        "Healthcare MCP Server",
        "http://mcp-tools.dstrmaysam-hkm-dev.local:9000/sse",
    ),
]
DASHBOARD_RANGE_OPTIONS = [
    ("30mins", "30m"),
    ("1hr", "1h"),
    ("3hr", "3h"),
    ("1 day", "1d"),
    ("3 days", "3d"),
    ("7 days", "7d"),
    ("all time", "all"),
]
DOCUMENT_CATEGORY_OPTIONS = [
    "general",
    "clinical_policy",
    "admin_policy",
    "compliance",
    "governance",
    "operations",
    "deterministic_lookup",
]
DOCUMENT_TYPE_OPTIONS = [
    "document",
    "policy",
    "sop",
    "pathway",
    "guideline",
    "procedure",
    "csv_table",
]
DOCUMENT_ACCESS_ROLE_PRESETS = [
    "staff",
    "staff, admin, manager",
    "doctor, nurse, clinical_governance, admin",
    "doctor, nurse, pharmacy, clinical_governance, admin",
    "staff, admin, manager, doctor, nurse, pharmacy, clinical_governance",
]


def _set_auth_cookie(token: str, max_age_seconds: int) -> None:
    components.html(
        f"""
        <script>
        const cookieName = {json.dumps(AUTH_COOKIE_NAME)};
        const token = {json.dumps(token)};
        const maxAge = {int(max_age_seconds)};
        const targetDocument = window.parent && window.parent.document ? window.parent.document : document;
        targetDocument.cookie = cookieName + "=" + encodeURIComponent(token)
            + "; Max-Age=" + maxAge + "; Path=/; SameSite=Lax";
        </script>
        """,
        height=0,
    )


def _clear_auth_cookie(*, reload_parent: bool = False) -> None:
    reload_script = "setTimeout(() => window.parent.location.reload(), 50);" if reload_parent else ""
    components.html(
        f"""
        <script>
        const cookieName = {json.dumps(AUTH_COOKIE_NAME)};
        const targetDocument = window.parent && window.parent.document ? window.parent.document : document;
        targetDocument.cookie = cookieName + "=; Max-Age=0; Path=/; SameSite=Lax";
        {reload_script}
        </script>
        """,
        height=0,
    )


def _read_auth_cookie() -> str | None:
    try:
        value = st.context.cookies.get(AUTH_COOKIE_NAME)
        return str(value) if value else None
    except Exception:
        return None


def sync_auth_cookie() -> None:
    # Keep authentication tied to the current Streamlit session. Browser cookie
    # auto-restore made stale tokens look like fresh successful logins.
    return


def store_user_context(data: dict[str, Any]) -> None:
    st.session_state.username = data.get("username")
    st.session_state.roles = data.get("roles", [])
    st.session_state.departments = data.get("departments", [])
    st.session_state.password_change_required = data.get("password_change_required", False)


def restore_login_from_cookie() -> None:
    st.session_state.pop("logout_requested", None)
    _clear_auth_cookie()
    return


def sign_out() -> None:
    for key in (
        "access_token",
        "access_token_expires_in",
        "username",
        "roles",
        "departments",
        "password_change_required",
        "session_id",
        "messages",
        "pending_chat_query",
    ):
        st.session_state.pop(key, None)
    st.session_state.logout_requested = True
    st.session_state.clear()
    st.session_state.logout_requested = True
    _clear_auth_cookie()
    st.rerun()


def api_headers() -> dict[str, str]:
    token = st.session_state.get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def raise_for_api_error(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = response.text
        title_match = re.search(r"<title>(.*?)</title>", detail or "", flags=re.IGNORECASE | re.DOTALL)
        heading_match = re.search(r"<h1>(.*?)</h1>", detail or "", flags=re.IGNORECASE | re.DOTALL)
        if title_match or heading_match:
            detail = html.unescape((heading_match or title_match).group(1)).strip()
    if isinstance(detail, list):
        detail = "; ".join(str(item.get("msg", item)) if isinstance(item, dict) else str(item) for item in detail)
    raise RuntimeError(f"{response.status_code}: {detail or response.reason}")


def post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{BACKEND_URL}{path}",
        json=payload,
        headers=api_headers(),
        timeout=300,
    )
    raise_for_api_error(response)
    return response.json()


def post_file(path: str, field_name: str, filename: str, data: bytes, content_type: str) -> dict[str, Any]:
    response = requests.post(
        f"{BACKEND_URL}{path}",
        files={field_name: (filename, data, content_type)},
        headers=api_headers(),
        timeout=300,
    )
    raise_for_api_error(response)
    return response.json()


def patch_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.patch(
        f"{BACKEND_URL}{path}",
        json=payload,
        headers=api_headers(),
        timeout=30,
    )
    raise_for_api_error(response)
    return response.json()


def get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    response = requests.get(f"{BACKEND_URL}{path}", params=params, headers=api_headers(), timeout=30)
    raise_for_api_error(response)
    return response.json()


def delete_json(path: str) -> dict[str, Any]:
    response = requests.delete(f"{BACKEND_URL}{path}", headers=api_headers(), timeout=30)
    raise_for_api_error(response)
    return response.json()


def render_manifest_status_overlay() -> None:
    if "access_token" not in st.session_state:
        return
    try:
        status = get_json("/system/manifest-status")
    except Exception:
        return
    if not isinstance(status, dict) or not status.get("requires_attention"):
        return
    message = str(status.get("message") or "Document manifest metadata needs attention.")
    missing_tables = [str(item) for item in status.get("missing_tables") or []]
    stale_tables = [str(item) for item in status.get("stale_tables") or []]
    missing_file_count = int(status.get("missing_file_count") or 0)
    details: list[str] = []
    if missing_tables:
        details.append(f"Missing table metadata: {', '.join(missing_tables[:8])}")
    if stale_tables:
        details.append(f"Stale table metadata: {', '.join(stale_tables[:8])}")
    if missing_file_count:
        details.append(f"Raw files missing from manifest: {missing_file_count}")
    error = str(status.get("error") or "").strip()
    if error:
        details.append(f"Error: {error}")
    st.warning(" ".join([message, *details]))


@st.cache_data(ttl=NEWS_REFRESH_SECONDS, show_spinner=False)
def fetch_news_payload() -> dict[str, Any]:
    response = requests.get(f"{BACKEND_URL}/news", timeout=20)
    raise_for_api_error(response)
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def get_news_articles() -> list[dict[str, Any]]:
    try:
        payload = fetch_news_payload()
    except Exception:
        return []
    articles = payload.get("articles")
    return [dict(article) for article in articles if isinstance(article, dict)] if isinstance(articles, list) else []


def schedule_news_refresh() -> None:
    components.html(
        f"""
        <script>
        setTimeout(() => window.parent.location.reload(), {NEWS_REFRESH_SECONDS * 1000});
        </script>
        """,
        height=0,
    )


def safe_article_url(article: dict[str, Any]) -> str:
    url = str(article.get("url") or "").strip()
    return url if url.startswith(("https://", "http://")) else "#"


def render_page_title(title: str) -> None:
    st.markdown(f'<div class="hka-page-title">{html.escape(title)}</div>', unsafe_allow_html=True)


def inject_chat_layout_css() -> None:
    st.markdown(
        """
        <style>
        .hka-chat-page-marker {
            display: none;
        }
        section[data-testid="stMain"] div[data-testid="stMainBlockContainer"]:has(.hka-chat-page-marker),
        div[data-testid="stAppViewContainer"] .main .block-container:has(.hka-chat-page-marker) {
            min-height: calc(100dvh - 3rem);
            padding-bottom: 5.25rem !important;
        }
        div[data-testid="stMainBlockContainer"]:has(.hka-chat-page-marker) .hka-page-title,
        div[data-testid="stAppViewContainer"] .main .block-container:has(.hka-chat-page-marker) .hka-page-title {
            margin-bottom: 0.45rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.hka-chat-window-marker) {
            height: max(360px, calc(100dvh - 11.25rem)) !important;
            max-height: none !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.hka-chat-window-marker) > div,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.hka-chat-window-marker) div[data-testid="stVerticalBlock"] {
            height: 100% !important;
            max-height: none !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.hka-chat-window-marker) div[data-testid="stVerticalBlock"] {
            overflow-y: auto;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_app_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --hka-accent: #0f766e;
            --hka-accent-strong: #0d9488;
            --hka-surface: #ffffff;
            --hka-surface-soft: #f2fbf8;
            --hka-border: #cfe8df;
            --hka-text: #102a43;
            --hka-muted: #52606d;
            --hka-shadow: 0 14px 36px rgba(15, 118, 110, 0.12);
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --hka-surface: #111827;
                --hka-surface-soft: #0f2f2b;
                --hka-border: #245c56;
                --hka-text: #e5f4f1;
                --hka-muted: #a7b8b4;
                --hka-shadow: 0 18px 42px rgba(0, 0, 0, 0.32);
            }
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(15, 148, 136, 0.13), transparent 30rem),
                linear-gradient(135deg, rgba(240, 253, 250, 0.62), rgba(255, 255, 255, 0));
        }
        @media (prefers-color-scheme: dark) {
            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(20, 184, 166, 0.12), transparent 30rem),
                    linear-gradient(135deg, rgba(8, 47, 73, 0.24), rgba(0, 0, 0, 0));
            }
        }
        div[data-testid="stSidebar"] {
            border-right: 1px solid var(--hka-border);
        }
        .block-container,
        section[data-testid="stMain"] div[data-testid="stMainBlockContainer"],
        div[data-testid="stAppViewContainer"] .main .block-container {
            padding-top: 0.25rem !important;
        }
        .stButton > button,
        .stForm button {
            border-radius: 8px;
            border-color: var(--hka-accent);
        }
        .stForm {
            border: 1px solid var(--hka-border);
            border-radius: 8px;
            box-shadow: var(--hka-shadow);
            padding: 1.1rem;
        }
        .hka-login-title {
            color: var(--hka-text);
            font-size: 2rem;
            font-weight: 720;
            letter-spacing: 0;
            line-height: 1.18;
            margin: 0 auto !important;
            max-width: 100%;
            overflow: visible;
            text-align: center;
        }
        .hka-login-header {
            margin: 0 auto 1.5rem;
            max-width: min(920px, 92vw);
            padding-top: clamp(2.75rem, 7vh, 4rem);
            text-align: center;
        }
        .hka-login-subtitle {
            color: var(--hka-muted);
            font-size: 1rem;
            margin: 0.55rem auto 0;
            max-width: 100%;
            text-align: center;
        }
        .hka-page-title {
            color: var(--hka-text);
            font-size: 2rem;
            font-weight: 720;
            letter-spacing: 0;
            line-height: 1.18;
            margin: 0 auto 0.8rem !important;
            text-align: center;
        }
        .hka-news-grid {
            display: grid;
            gap: 16px;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            margin-top: 16px;
        }
        .hka-news-card {
            background: var(--hka-surface);
            border: 1px solid var(--hka-border);
            border-radius: 8px;
            box-shadow: var(--hka-shadow);
            color: var(--hka-text);
            display: flex;
            flex-direction: column;
            min-height: 100%;
            overflow: hidden;
            text-decoration: none;
            transition: border-color 160ms ease, transform 160ms ease;
        }
        .hka-news-card:hover {
            border-color: var(--hka-accent-strong);
            transform: translateY(-2px);
        }
        .hka-news-card img {
            aspect-ratio: 16 / 9;
            object-fit: cover;
            width: 100%;
        }
        .hka-news-card-content {
            display: flex;
            flex: 1;
            flex-direction: column;
            gap: 8px;
            padding: 14px;
        }
        .hka-news-meta {
            color: var(--hka-accent-strong);
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
        }
        .hka-news-title {
            color: var(--hka-text);
            font-size: 1rem;
            font-weight: 740;
            line-height: 1.3;
        }
        .hka-news-summary {
            color: var(--hka-muted);
            font-size: 0.9rem;
            line-height: 1.45;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.hka-chat-window-marker) {
            height: calc(100dvh - 11.25rem) !important;
            min-height: 390px !important;
            max-height: calc(100dvh - 11.25rem) !important;
            margin-bottom: 0.65rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.hka-chat-window-marker),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.hka-chat-window-marker) > div,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.hka-chat-window-marker) div[data-testid="stVerticalBlock"] {
            height: 100% !important;
            overflow-y: auto !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.hka-chat-window-marker) div[data-testid="stVerticalBlock"] {
            padding-bottom: 0.75rem !important;
        }
        div[data-testid="stVerticalBlock"]:has(.hka-chat-window-marker) {
            gap: 0.55rem !important;
        }
        div[data-testid="stChatInput"] {
            margin-top: 0 !important;
        }
        div[data-testid="stChatInput"] > div {
            padding-top: 0.35rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_login_news_carousel() -> None:
    articles = get_news_articles()
    if not articles:
        return

    cards = []
    for article in articles[:10]:
        title = html.escape(str(article.get("title") or "Guardian NHS story"))
        summary = html.escape(str(article.get("summary") or ""))
        section = html.escape(str(article.get("section") or "NHS"))
        published = html.escape(str(article.get("published_at") or "")[:10])
        url = html.escape(safe_article_url(article), quote=True)
        thumbnail = html.escape(str(article.get("thumbnail") or ""), quote=True)
        image = f'<img src="{thumbnail}" alt="" />' if thumbnail.startswith(("https://", "http://")) else ""
        cards.append(
            f"""
            <a class="news-card" href="{url}" target="_blank" rel="noopener noreferrer">
                {image}
                <span class="meta">{section}{' | ' + published if published else ''}</span>
                <strong>{title}</strong>
                <span class="summary">{summary}</span>
            </a>
            """
        )

    carousel_html = f"""
    <style>
    :root {{
        color-scheme: light dark;
        --news-surface: #ffffff;
        --news-border: #cfe8df;
        --news-text: #102a43;
        --news-muted: #52606d;
        --news-accent: #0d9488;
    }}
    @media (prefers-color-scheme: dark) {{
        :root {{
            --news-surface: #111827;
            --news-border: #245c56;
            --news-text: #e5f4f1;
            --news-muted: #a7b8b4;
            --news-accent: #2dd4bf;
        }}
    }}
    .news-shell {{
        margin-top: 22px;
        overflow: hidden;
        width: 100%;
    }}
    .news-track {{
        display: flex;
        gap: 14px;
        width: max-content;
        animation: scrollNews 55s linear infinite;
    }}
    .news-track:hover {{
        animation-play-state: paused;
    }}
    .news-card {{
        background: var(--news-surface);
        border: 1px solid var(--news-border);
        border-radius: 8px;
        color: var(--news-text);
        display: flex;
        flex-direction: column;
        gap: 8px;
        min-height: 230px;
        padding: 14px;
        text-decoration: none;
        width: 285px;
    }}
    .news-card img {{
        aspect-ratio: 16 / 9;
        border-radius: 6px;
        object-fit: cover;
        width: 100%;
    }}
    .news-card strong {{
        font: 700 15px/1.32 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .news-card .meta {{
        color: var(--news-accent);
        font: 600 11px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        text-transform: uppercase;
    }}
    .news-card .summary {{
        color: var(--news-muted);
        font: 13px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    @keyframes scrollNews {{
        from {{ transform: translateX(0); }}
        to {{ transform: translateX(-50%); }}
    }}
    </style>
    <div class="news-shell">
        <div class="news-track">
            {''.join(cards)}
            {''.join(cards)}
        </div>
    </div>
    """
    components.html(carousel_html, height=290, scrolling=False)


def news_card_html(article: dict[str, Any]) -> str:
    title = html.escape(str(article.get("title") or "Guardian NHS story"))
    summary = html.escape(str(article.get("summary") or ""))
    section = html.escape(str(article.get("section") or "NHS"))
    published = html.escape(str(article.get("published_at") or "")[:10])
    url = html.escape(safe_article_url(article), quote=True)
    thumbnail = html.escape(str(article.get("thumbnail") or ""), quote=True)
    meta = f"{section} | {published}" if published else section
    image = f'<img src="{thumbnail}" alt="" />' if thumbnail.startswith(("https://", "http://")) else ""
    return (
        f'<a class="hka-news-card" href="{url}" target="_blank" rel="noopener noreferrer">'
        f"{image}"
        '<span class="hka-news-card-content">'
        f'<span class="hka-news-meta">{meta}</span>'
        f'<span class="hka-news-title">{title}</span>'
        f'<span class="hka-news-summary">{summary}</span>'
        "</span>"
        "</a>"
    )


def render_news_page() -> None:
    schedule_news_refresh()
    render_page_title("NHS news")
    articles = get_news_articles()
    if not articles:
        st.info("No NHS news articles are available right now.")
        return
    st.markdown(
        f'<div class="hka-news-grid">{"".join(news_card_html(article) for article in articles)}</div>',
        unsafe_allow_html=True,
    )


def warm_document_manifest_cache() -> None:
    if st.session_state.get("password_change_required"):
        return
    try:
        documents = get_json("/documents")
        st.session_state.document_cache = list(documents) if isinstance(documents, list) else []
        st.session_state.document_cache_loaded = True
        st.session_state.document_cache_error = None
    except Exception as exc:
        st.session_state.document_cache = []
        st.session_state.document_cache_loaded = False
        st.session_state.document_cache_error = str(exc)


def store_login(data: dict[str, Any]) -> None:
    st.session_state.access_token = data["access_token"]
    st.session_state.access_token_expires_in = data.get("expires_in", AUTH_COOKIE_DEFAULT_MAX_AGE_SECONDS)
    store_user_context(data)


def parse_departments(raw: str) -> list[str]:
    departments = []
    for item in raw.split(","):
        value = item.strip().lower()
        if value and value not in departments:
            departments.append(value)
    return departments


def render_password_change() -> None:
    render_page_title("Change password")
    with st.form("change-password"):
        current_password = st.text_input("Current password", type="password")
        new_password = st.text_input("New password", type="password")
        confirm_password = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password")
    if submitted:
        if new_password != confirm_password:
            st.error("New passwords do not match")
            return
        if len(new_password) < MIN_PASSWORD_LENGTH:
            st.error(f"New password must be at least {MIN_PASSWORD_LENGTH} characters")
            return
        try:
            data = post_json(
                "/auth/change-password",
                {"current_password": current_password, "new_password": new_password},
            )
            store_login(data)
            warm_document_manifest_cache()
            st.success("Password updated")
            st.rerun()
        except Exception as exc:
            st.error(f"Password update failed: {exc}")


def render_admin_users() -> None:
    render_page_title("Users")
    with st.expander("Create user", expanded=True):
        with st.form("create-user"):
            username = st.text_input("Username")
            temporary_password = st.text_input("Temporary password", type="password")
            roles = st.multiselect("Roles", KNOWN_ROLES, default=["staff"])
            departments = st.text_input("Departments", placeholder="clinical_governance, operations")
            submitted = st.form_submit_button("Create user")
        if submitted:
            if len(temporary_password) < MIN_PASSWORD_LENGTH:
                st.error(f"Temporary password must be at least {MIN_PASSWORD_LENGTH} characters")
                return
            if not roles:
                st.error("Select at least one role")
                return
            try:
                post_json(
                    "/admin/users",
                    {
                        "username": username,
                        "temporary_password": temporary_password,
                        "roles": roles,
                        "departments": parse_departments(departments),
                    },
                )
                st.success("User created")
                st.rerun()
            except Exception as exc:
                st.error(f"Create user failed: {exc}")

    try:
        users = get_json("/admin/users")
    except Exception as exc:
        st.error(f"Unable to load users: {exc}")
        return

    for user in users:
        username = user["username"]
        with st.expander(username):
            st.caption("Password change required" if user.get("password_change_required") else "Password current")
            with st.form(f"profile-{username}"):
                selected_roles = st.multiselect(
                    "Roles",
                    KNOWN_ROLES,
                    default=[role for role in user.get("roles", []) if role in KNOWN_ROLES],
                    key=f"roles-{username}",
                )
                departments = st.text_input(
                    "Departments",
                    value=", ".join(user.get("departments", [])),
                    key=f"departments-{username}",
                )
                save_profile = st.form_submit_button("Save profile")
            if save_profile:
                try:
                    patch_json(
                        f"/admin/users/{username}",
                        {
                            "roles": selected_roles,
                            "departments": parse_departments(departments),
                        },
                    )
                    st.success("Profile saved")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Save profile failed: {exc}")

            with st.form(f"reset-{username}"):
                temporary_password = st.text_input(
                    "Temporary password",
                    type="password",
                    key=f"reset-password-{username}",
                )
                reset_password = st.form_submit_button("Reset password")
            if reset_password:
                if len(temporary_password) < MIN_PASSWORD_LENGTH:
                    st.error(f"Temporary password must be at least {MIN_PASSWORD_LENGTH} characters")
                    return
                try:
                    post_json(
                        f"/admin/users/{username}/reset-password",
                        {"temporary_password": temporary_password},
                    )
                    st.success("Password reset")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Password reset failed: {exc}")


def render_admin_settings() -> None:
    render_page_title("Settings")
    try:
        settings = get_json("/admin/settings/tool-execution")
    except Exception as exc:
        st.error(f"Unable to load tool execution settings: {exc}")
        return
    if not isinstance(settings, dict):
        st.error("Tool execution settings response was not valid.")
        return

    st.session_state.tool_execution_settings = dict(settings)
    mode_options = ["local", "mcp"]
    current_mode = str(settings.get("tool_execution_mode") or "local").strip().lower()
    mode_index = mode_options.index(current_mode) if current_mode in mode_options else 0
    current_mcp_server_url = str(settings.get("mcp_server_url") or "").strip()
    mcp_server_url_options = list(MCP_SERVER_URL_OPTIONS)
    known_mcp_urls = {url for _, url in mcp_server_url_options}
    if current_mcp_server_url and current_mcp_server_url not in known_mcp_urls:
        mcp_server_url_options.append(("Current custom URL", current_mcp_server_url))
    mcp_url_values = [url for _, url in mcp_server_url_options]
    mcp_url_index = mcp_url_values.index(current_mcp_server_url) if current_mcp_server_url in mcp_url_values else 0

    with st.form("tool-execution-settings"):
        mode = st.selectbox("Tool execution mode", mode_options, index=mode_index)
        mcp_server_url = st.selectbox(
            "MCP server URL",
            options=mcp_url_values,
            index=mcp_url_index,
            format_func=lambda value: next(
                (f"{label}: {url}" for label, url in mcp_server_url_options if url == value),
                str(value),
            ),
        )
        mcp_project_id = st.text_input(
            "MCP project ID",
            value=str(settings.get("mcp_project_id") or "dstrmaysam-healthcare-knowledge-multi-agent"),
        )
        timeout = st.number_input(
            "MCP tool timeout seconds",
            min_value=1,
            max_value=300,
            value=int(settings.get("mcp_tool_timeout_seconds") or 30),
            step=1,
        )
        fallback_to_local = st.toggle(
            "Fallback to local tools if MCP fails",
            value=bool(settings.get("mcp_tool_fallback_to_local")),
        )
        save = st.form_submit_button("Save settings")

    if save:
        try:
            updated = patch_json(
                "/admin/settings/tool-execution",
                {
                    "tool_execution_mode": mode,
                    "mcp_server_url": mcp_server_url.strip(),
                    "mcp_project_id": mcp_project_id.strip(),
                    "mcp_tool_timeout_seconds": int(timeout),
                    "mcp_tool_fallback_to_local": bool(fallback_to_local),
                },
            )
            st.session_state.tool_execution_settings = dict(updated)
            st.success("Tool execution settings saved")
            st.rerun()
        except Exception as exc:
            st.error(f"Save settings failed: {exc}")

    with st.expander("Current effective values", expanded=True):
        st.json(st.session_state.get("tool_execution_settings", settings))


def count_rows(counts: dict[str, Any], label: str) -> list[dict[str, Any]]:
    return [
        {label: str(name), "Count": int(value)}
        for name, value in sorted(counts.items(), key=lambda item: int(item[1]), reverse=True)
    ]


def latency_rows(values: dict[str, Any], labels: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for key, label in labels.items():
        try:
            value = int(values.get(key) or 0)
        except Exception:
            value = 0
        if value:
            rows.append({"Phase": label, "Latency ms": value})
    rows.sort(key=lambda row: int(row["Latency ms"]), reverse=True)
    return rows


def latency_section_rows(sections: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for section, metrics in sections.items():
        if not isinstance(metrics, dict):
            continue
        for metric, value in metrics.items():
            if isinstance(value, (dict, list)):
                display_value = json.dumps(value)
            else:
                display_value = str(value)
            rows.append(
                {
                    "Section": str(section).replace("_", " ").title(),
                    "Metric": str(metric),
                    "Value": display_value,
                }
            )
    return rows


def raw_latency_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for metric, value in sorted(metrics.items()):
        try:
            latency_ms = int(value or 0)
        except Exception:
            continue
        rows.append({"Metric": str(metric), "Latency ms": latency_ms})
    rows.sort(key=lambda row: int(row["Latency ms"]), reverse=True)
    return rows


def counter_rows(counters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for metric, value in sorted(counters.items()):
        try:
            count = int(value or 0)
        except Exception:
            continue
        rows.append({"Metric": str(metric), "Value": count})
    return rows


def tool_latency_rows(tool_timings: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for item in tool_timings:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "Tool": item.get("tool", ""),
                "Total ms": int(item.get("total_ms") or 0),
                "Index check ms": int(item.get("index_check_ms") or 0),
                "Index created": int(item.get("index_created") or 0),
                "Catalog ms": int(item.get("catalog_ms") or 0),
                "Retrieval ms": int(item.get("retrieval_search_ms") or 0),
                "Embedding ms": int(item.get("embedding_ms") or 0),
                "OpenSearch ms": int(item.get("opensearch_ms") or 0),
                "Neighbor ms": int(item.get("neighbor_ms") or 0),
                "Access filter ms": int(item.get("access_filter_ms") or 0),
                "Vector hits": int(item.get("vector_hits") or 0),
                "Keyword hits": int(item.get("keyword_hits") or 0),
                "Neighbor hits": int(item.get("neighbor_hits") or 0),
                "Returned hits": int(item.get("returned_hits") or 0),
            }
        )
    return rows


def dashboard_agent_name_for_tool(tool_name: str) -> str:
    if tool_name in {"postgres_deterministic_lookup", "table_lookup", "formulary_table_lookup", "calendar_rota_lookup"}:
        return "DeterministicLookupAgent"
    if tool_name in {"rag_search", "document_search"}:
        return "RAGAgent"
    if tool_name == "policy_search":
        return "PolicyAgent"
    if tool_name in {"document_catalog", "catalogue_search"}:
        return "CatalogAgent"
    if tool_name == "safety_guard":
        return "SafetyAgent"
    return "ToolAgent"


def inferred_agent_flow(item: dict[str, Any]) -> list[dict[str, Any]]:
    existing = item.get("agent_flow") if isinstance(item.get("agent_flow"), list) else []
    existing_steps = [step for step in existing if isinstance(step, dict)]
    if any(step.get("agent") == "SupervisorAgent" and step.get("decision") == "route" for step in existing_steps):
        return existing_steps

    flow: list[dict[str, Any]] = []
    supervisor_decisions = (
        item.get("supervisor_decisions")
        if isinstance(item.get("supervisor_decisions"), list)
        else []
    )
    for decision in supervisor_decisions:
        if isinstance(decision, dict):
            flow.append(dict(decision))

    tool_flow = item.get("tool_flow") if isinstance(item.get("tool_flow"), list) else []
    tools_used = [str(tool) for tool in item.get("tools_used", [])] if isinstance(item.get("tools_used"), list) else []
    selected_tools = [
        str(step.get("tool") or "")
        for step in tool_flow
        if isinstance(step, dict) and step.get("selected_by_agent") and step.get("tool")
    ]
    selected_tools.extend(tools_used)
    selected_tools = list(dict.fromkeys(tool for tool in selected_tools if tool))

    existing_routes = {
        (str(step.get("selected_agent") or ""), str(step.get("tool") or ""))
        for step in flow
        if step.get("agent") == "SupervisorAgent" and step.get("decision") == "route"
    }
    for tool in selected_tools:
        agent = dashboard_agent_name_for_tool(tool)
        route_key = (agent, tool)
        if route_key not in existing_routes:
            flow.append(
                {
                    "agent": "SupervisorAgent",
                    "kind": "supervisor",
                    "decision": "route",
                    "selected_agent": agent,
                    "tool": tool,
                    "query": item.get("query", ""),
                    "reason": "reconstructed_from_tool_metadata",
                }
            )
        matching_tool = next(
            (
                step
                for step in tool_flow
                if isinstance(step, dict) and str(step.get("tool") or "") == tool
            ),
            {},
        )
        flow.append(
            {
                "agent": agent,
                "kind": "specialist",
                "tool": tool,
                "query": matching_tool.get("query") or item.get("query", ""),
                "status": "reconstructed",
                "latency_ms": int(matching_tool.get("latency_ms") or 0) if isinstance(matching_tool, dict) else 0,
                "source_count": int(matching_tool.get("returned_hits") or 0) if isinstance(matching_tool, dict) else 0,
            }
        )

    agents_used = [str(agent) for agent in item.get("agents_used", [])] if isinstance(item.get("agents_used"), list) else []
    if item.get("answer") and ("SynthesisAgent" in agents_used or selected_tools):
        flow.append(
            {
                "agent": "SynthesisAgent",
                "kind": "synthesis",
                "status": "answered",
                "latency_ms": int((item.get("agent_latencies_ms") or {}).get("SynthesisAgent") or 0)
                if isinstance(item.get("agent_latencies_ms"), dict)
                else 0,
            }
        )

    return flow or existing_steps


def _related_tool_steps(tool_flow: list[Any], selected_tool: str) -> list[dict[str, Any]]:
    related = []
    seen: set[str] = set()
    for step in tool_flow:
        if not isinstance(step, dict):
            continue
        tool = str(step.get("tool") or "")
        helper_for = str(step.get("helper_for") or "")
        if tool != selected_tool and helper_for != selected_tool:
            continue
        key = json.dumps(step, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        related.append(step)
    if selected_tool and not any(str(step.get("tool") or "") == selected_tool for step in related):
        related.append({"tool": selected_tool, "kind": "agent_tool", "selected_by_agent": True})
    return related


def _matching_specialist_step(agent_flow: list[Any], selected_agent: str, selected_tool: str) -> dict[str, Any]:
    for step in agent_flow:
        if not isinstance(step, dict):
            continue
        if step.get("kind") != "specialist":
            continue
        if selected_agent and str(step.get("agent") or "") != selected_agent:
            continue
        if selected_tool and str(step.get("tool") or "") != selected_tool:
            continue
        return step
    return {}


def render_agent_decision_tree(agent_flow: list[Any], tool_flow: list[Any]) -> None:
    flow_steps = [step for step in agent_flow if isinstance(step, dict)]
    route_decisions = [
        step
        for step in flow_steps
        if step.get("agent") == "SupervisorAgent" and step.get("decision") == "route"
    ]
    synthesis_steps = [step for step in flow_steps if step.get("agent") == "SynthesisAgent"]
    if not route_decisions and not synthesis_steps:
        st.caption("No supervisor decision tree captured for this query.")
        return

    branches = []
    for index, decision in enumerate(route_decisions, start=1):
        selected_agent = str(decision.get("selected_agent") or "SpecialistAgent")
        selected_tool = str(decision.get("tool") or "")
        specialist = _matching_specialist_step(flow_steps, selected_agent, selected_tool)
        tool_steps = _related_tool_steps(tool_flow, selected_tool)
        if not tool_steps and selected_tool:
            tool_steps = [{"tool": selected_tool, "kind": "agent_tool", "selected_by_agent": True}]

        tool_cards = []
        for tool_step in tool_steps:
            tool = str(tool_step.get("tool") or "tool")
            kind = str(tool_step.get("kind") or "tool").replace("_", " ").title()
            helper_for = str(tool_step.get("helper_for") or "")
            selected_by_agent = bool(tool_step.get("selected_by_agent"))
            latency = int(tool_step.get("latency_ms") or 0)
            returned_hits = tool_step.get("returned_hits")
            candidate_count = tool_step.get("candidate_count")
            detail_parts = []
            if helper_for:
                detail_parts.append(f"helper for {helper_for}")
            elif selected_by_agent:
                detail_parts.append("selected by agent")
            if candidate_count not in (None, ""):
                detail_parts.append(f"candidates {candidate_count}")
            if returned_hits not in (None, ""):
                detail_parts.append(f"hits {returned_hits}")
            if latency:
                detail_parts.append(f"{latency} ms")
            tool_cards.append(
                f"""
                <div class="tree-node tree-tool">
                    <div class="tree-kicker">Tool</div>
                    <div class="tree-name">{html.escape(tool)}</div>
                    <div class="tree-detail">{html.escape(' | '.join(detail_parts) or kind)}</div>
                </div>
                """
            )

        specialist_status = str(specialist.get("status") or "selected")
        specialist_latency = int(specialist.get("latency_ms") or 0)
        source_count = specialist.get("source_count")
        specialist_detail = [specialist_status]
        if selected_tool:
            specialist_detail.append(f"tool {selected_tool}")
        if source_count not in (None, ""):
            specialist_detail.append(f"sources {source_count}")
        if specialist_latency:
            specialist_detail.append(f"{specialist_latency} ms")
        branches.append(
            f"""
            <div class="tree-branch">
                <div class="tree-node tree-supervisor">
                    <div class="tree-kicker">Step {index} | Supervisor decision</div>
                    <div class="tree-name">SupervisorAgent</div>
                    <div class="tree-detail">
                        routes to {html.escape(selected_agent)}
                        {html.escape(' using ' + selected_tool if selected_tool else '')}
                    </div>
                    <div class="tree-reason">{html.escape(str(decision.get("reason") or ""))}</div>
                </div>
                <div class="tree-children">
                    <div class="tree-node tree-agent">
                        <div class="tree-kicker">Chosen agent</div>
                        <div class="tree-name">{html.escape(selected_agent)}</div>
                        <div class="tree-detail">{html.escape(' | '.join(specialist_detail))}</div>
                    </div>
                    <div class="tree-children tree-tool-list">
                        {''.join(tool_cards) or '<div class="tree-empty">No tool usage captured.</div>'}
                    </div>
                </div>
            </div>
            """
        )

    synthesis_cards = []
    for synthesis in synthesis_steps:
        latency = int(synthesis.get("latency_ms") or 0)
        detail = str(synthesis.get("status") or "answered")
        if latency:
            detail = f"{detail} | {latency} ms"
        synthesis_cards.append(
            f"""
            <div class="tree-branch">
                <div class="tree-node tree-synthesis">
                    <div class="tree-kicker">Final response</div>
                    <div class="tree-name">SynthesisAgent</div>
                    <div class="tree-detail">{html.escape(detail)}</div>
                </div>
            </div>
            """
        )

    st.html(
        textwrap.dedent(f"""
        <style>
        .decision-tree {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: #e5e7eb;
            padding: 4px 0;
        }}
        .tree-branch {{
            margin: 0 0 10px 0;
        }}
        .tree-node {{
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 8px 10px;
            background: #111827;
            max-width: 860px;
        }}
        .tree-supervisor {{
            border-left: 4px solid #60a5fa;
        }}
        .tree-agent {{
            border-left: 4px solid #34d399;
            margin-top: 8px;
        }}
        .tree-tool {{
            border-left: 4px solid #fbbf24;
            margin-top: 6px;
        }}
        .tree-synthesis {{
            border-left: 4px solid #a78bfa;
        }}
        .tree-children {{
            margin-left: 28px;
            padding-left: 16px;
            border-left: 1px solid #334155;
        }}
        .tree-tool-list {{
            margin-top: 2px;
        }}
        .tree-kicker {{
            color: #93c5fd;
            font-size: 12px;
            line-height: 15px;
            margin-bottom: 3px;
        }}
        .tree-name {{
            font-size: 15px;
            font-weight: 700;
            line-height: 18px;
            margin-bottom: 4px;
        }}
        .tree-detail, .tree-reason, .tree-empty {{
            color: #cbd5e1;
            font-size: 12px;
            line-height: 15px;
        }}
        .tree-reason {{
            color: #94a3b8;
            margin-top: 5px;
        }}
        </style>
        <div class="decision-tree">
            {''.join(branches)}
            {''.join(synthesis_cards)}
        </div>
        """).strip(),
    )


def ragas_detail_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    ragas = item.get("ragas") if isinstance(item.get("ragas"), dict) else {}
    metrics = [
        ("Faithfulness", "ragas_faithfulness"),
        ("Answer relevancy", "ragas_answer_relevancy"),
        ("Context precision", "ragas_context_precision"),
        ("Context recall", "ragas_context_recall"),
    ]
    return [
        {
            "Metric": label,
            "Score": format_score(ragas.get(key)),
        }
        for label, key in metrics
    ]


def render_ragas_details(item: dict[str, Any]) -> None:
    status = str(item.get("ragas_status") or "").strip()
    provider = str(item.get("ragas_provider") or "").strip()
    error = str(item.get("ragas_error") or "").strip()
    ragas = item.get("ragas") if isinstance(item.get("ragas"), dict) else {}
    has_scores = any(ragas.get(key) is not None for key in [
        "ragas_faithfulness",
        "ragas_answer_relevancy",
        "ragas_context_precision",
        "ragas_context_recall",
    ])
    if not status:
        status = "completed" if has_scores else "pending"
    st.markdown("**RAGAS evaluation**")
    provider_text = f" | Provider: {provider}" if provider else ""
    st.caption(f"Status: {status}{provider_text}")
    if error:
        st.warning(f"RAGAS detail: {error}")
    if has_scores:
        st.dataframe(ragas_detail_rows(item), hide_index=True, use_container_width=True)
    elif status == "pending":
        st.info("RAGAS scoring is pending for this query.")
    else:
        st.info("No RAGAS scores are available for this query.")


def render_query_detail(item: dict[str, Any]) -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stDialog"] div[role="dialog"] {
            width: 60vw;
            max-width: 60vw;
        }
        @media (max-width: 1100px) {
            div[data-testid="stDialog"] div[role="dialog"] {
                width: 92vw;
                max-width: 92vw;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    display_agent_flow = inferred_agent_flow(item)
    display_supervisor_decisions = (
        item.get("supervisor_decisions")
        if isinstance(item.get("supervisor_decisions"), list) and item.get("supervisor_decisions")
        else [
            step
            for step in display_agent_flow
            if isinstance(step, dict) and step.get("agent") == "SupervisorAgent"
        ]
    )
    detail_columns = st.columns(5)
    detail_columns[0].metric("Latency", f"{item.get('latency_ms', 0)} ms")
    detail_columns[1].metric("Sources", item.get("source_count", 0))
    detail_columns[2].metric("Input tokens", item.get("input_tokens") or 0)
    detail_columns[3].metric("Output tokens", item.get("output_tokens") or 0)
    detail_columns[4].metric("Total tokens", item.get("total_tokens") or 0)
    st.caption(f"Trace ID: {item.get('trace_id') or 'unavailable'}")
    st.caption(f"Session ID: {item.get('session_id')}")
    st.caption(f"Routing: {item.get('chat_execution_mode_label') or 'Supervisor'}")
    st.caption(f"Agent mode: {item.get('agent_mode') or 'unknown'}")
    tool_execution_mode = str(item.get("tool_execution_mode") or "").strip().lower()
    tool_execution_location = str(item.get("tool_execution_location") or "").strip()
    if not tool_execution_location:
        tool_execution_location = "MCP server" if tool_execution_mode == "mcp" else "Backend local tools" if tool_execution_mode else "Unknown"
    tool_location_detail = tool_execution_location
    if tool_execution_mode:
        tool_location_detail = f"{tool_location_detail} ({tool_execution_mode})"
    if tool_execution_mode == "mcp":
        mcp_target = str(item.get("mcp_server_url") or item.get("mcp_project_id") or "").strip()
        if mcp_target:
            tool_location_detail = f"{tool_location_detail} - {mcp_target}"
    st.caption(f"Tool execution: {tool_location_detail}")
    tool_execution_records = (
        item.get("tool_execution_records")
        if isinstance(item.get("tool_execution_records"), list)
        else []
    )
    if tool_execution_records:
        execution_rows = []
        for record in tool_execution_records:
            if not isinstance(record, dict):
                continue
            execution_rows.append(
                {
                    "tool": record.get("tool", ""),
                    "status": record.get("status", ""),
                    "actual location": record.get("actual_location", ""),
                    "configured mode": record.get("configured_mode", ""),
                    "latency ms": record.get("latency_ms", 0),
                    "mcp error": record.get("mcp_error", ""),
                    "reason": record.get("reason", ""),
                }
            )
        if execution_rows:
            st.markdown("**Tool execution records**")
            st.dataframe(execution_rows, hide_index=True, use_container_width=True)
    st.caption(f"Agents: {item.get('agent_flow_summary') or ', '.join(item.get('agents_used') or []) or 'unavailable'}")
    if display_supervisor_decisions:
        st.markdown("**Supervisor decisions**")
        st.dataframe(display_supervisor_decisions, hide_index=True, use_container_width=True)
    st.markdown("**Multi-agent decision tree**")
    render_agent_decision_tree(display_agent_flow, item.get("tool_flow") or [])
    render_ragas_details(item)
    st.markdown("**Question**")
    st.write(item.get("query", ""))
    st.markdown("**Answer**")
    st.write(item.get("answer", ""))
    latency_breakdown = item.get("latency_breakdown") if isinstance(item.get("latency_breakdown"), dict) else {}
    if latency_breakdown:
        with st.expander("Timing details", expanded=False):
            top_level = latency_breakdown.get("top_level") if isinstance(latency_breakdown.get("top_level"), dict) else {}
            agent_detail = latency_breakdown.get("agent_detail") if isinstance(latency_breakdown.get("agent_detail"), dict) else {}
            top_level_rows = latency_rows(
                top_level,
                {
                    "agent_execution_ms": "Agent execution",
                    "history_load_ms": "History load",
                    "trace_setup_ms": "Langfuse trace setup",
                    "prompt_load_ms": "Prompt load",
                    "initial_safety_ms": "Initial safety",
                    "response_guardrail_ms": "Response guardrail",
                    "final_safety_ms": "Final safety",
                    "history_save_ms": "History save",
                    "unattributed_ms": "Other",
                },
            )
            timing_agent_rows = latency_rows(
                agent_detail,
                {
                    "llm_total_ms": "LLM calls",
                    "llm_tool_choice_ms": "LLM tool choice",
                    "llm_final_ms": "LLM final answer",
                    "llm_direct_answer_ms": "LLM direct answer",
                    "llm_setup_ms": "LLM setup",
                    "fast_llm_setup_ms": "Fast LLM setup",
                    "langfuse_callbacks_ms": "Langfuse callbacks",
                    "catalog_ms": "Document catalog",
                    "index_check_ms": "OpenSearch index check",
                    "retrieval_search_ms": "Retrieval search",
                    "embedding_ms": "Embedding",
                    "opensearch_ms": "OpenSearch",
                    "neighbor_ms": "Neighbor chunks",
                    "access_filter_ms": "Access filtering",
                },
            )
            timing_columns = st.columns(2)
            with timing_columns[0]:
                st.markdown("**Latency breakdown**")
                if top_level_rows:
                    st.dataframe(top_level_rows, hide_index=True, use_container_width=True)
                else:
                    st.caption("No phase timings captured.")
            with timing_columns[1]:
                st.markdown("**Agent detail**")
                if timing_agent_rows:
                    st.dataframe(timing_agent_rows, hide_index=True, use_container_width=True)
                else:
                    st.caption("No agent detail timings captured.")
            tool_rows = tool_latency_rows(latency_breakdown.get("tool_timings") or [])
            if tool_rows:
                st.markdown("**Tool timings**")
                st.dataframe(tool_rows, hide_index=True, use_container_width=True)
            section_rows = latency_section_rows(
                latency_breakdown.get("sections")
                if isinstance(latency_breakdown.get("sections"), dict)
                else {}
            )
            if section_rows:
                st.markdown("**Detailed latency sections**")
                st.dataframe(section_rows, hide_index=True, use_container_width=True)
            raw_rows = raw_latency_rows(
                latency_breakdown.get("raw_timing_metrics")
                if isinstance(latency_breakdown.get("raw_timing_metrics"), dict)
                else {}
            )
            if raw_rows:
                st.markdown("**All captured timing metrics**")
                st.dataframe(raw_rows, hide_index=True, use_container_width=True)
            total_rows = counter_rows(
                latency_breakdown.get("tool_timing_totals")
                if isinstance(latency_breakdown.get("tool_timing_totals"), dict)
                else {}
            )
            if total_rows:
                st.markdown("**Tool totals and hit counts**")
                st.dataframe(total_rows, hide_index=True, use_container_width=True)
    with st.expander("Tools, sources, and raw metadata", expanded=False):
        st.json(
            {
                "tools_used": item.get("tools_used", []),
                "tool_flow": item.get("tool_flow", []),
                "agents_used": item.get("agents_used", []),
                "agent_flow": item.get("agent_flow", []),
                "display_agent_flow": display_agent_flow,
                "supervisor_decisions": item.get("supervisor_decisions", []),
                "agent_latencies_ms": item.get("agent_latencies_ms", {}),
                "agent_errors": item.get("agent_errors", []),
                "source_document_keys": item.get("source_document_keys", []),
                "latency_breakdown": item.get("latency_breakdown", {}),
                "chat_execution_mode": item.get("chat_execution_mode"),
                "chat_execution_mode_label": item.get("chat_execution_mode_label"),
                "tool_execution_mode": item.get("tool_execution_mode"),
                "tool_execution_location": item.get("tool_execution_location"),
                "mcp_server_url": item.get("mcp_server_url"),
                "mcp_project_id": item.get("mcp_project_id"),
                "agent_mode": item.get("agent_mode"),
                "ragas": item.get("ragas", {}),
                "ragas_status": item.get("ragas_status"),
                "ragas_provider": item.get("ragas_provider"),
                "langfuse_ragas_published": item.get("langfuse_ragas_published"),
                "guardrail_applied": item.get("guardrail_applied"),
                "guardrail_reason": item.get("guardrail_reason"),
                "safety": item.get("safety", {}),
            }
        )


def render_admin_dashboard() -> None:
    render_page_title("Dashboard")

    user_options = ["all"]
    try:
        users_payload = get_json("/admin/users")
        if isinstance(users_payload, list):
            user_options.extend(
                str(user.get("username"))
                for user in users_payload
                if isinstance(user, dict) and user.get("username")
            )
    except Exception:
        pass
    user_options = list(dict.fromkeys(user_options))

    filter_columns = st.columns([1, 1, 2])
    range_labels = [label for label, _ in DASHBOARD_RANGE_OPTIONS]
    selected_range_label = filter_columns[0].selectbox(
        "Range",
        range_labels,
        index=range_labels.index("all time"),
        key="dashboard_range_filter",
    )
    selected_range = dict(DASHBOARD_RANGE_OPTIONS)[selected_range_label]
    selected_user_label = filter_columns[1].selectbox(
        "User",
        ["All users", *[username for username in user_options if username != "all"]],
        key="dashboard_user_filter",
    )
    selected_user = "all" if selected_user_label == "All users" else selected_user_label

    try:
        payload = get_json(
            "/admin/dashboard",
            params={
                "limit": 500,
                "range": selected_range,
                "user_id": selected_user,
            },
        )
    except Exception as exc:
        st.error(f"Unable to load dashboard: {exc}")
        return

    if not isinstance(payload, dict):
        st.error("Unexpected dashboard response")
        return

    summary = payload.get("summary") or {}
    queries = payload.get("queries") or []
    ragas_summary = summary.get("ragas") or {}
    metric_columns = st.columns(8)
    metric_columns[0].metric("Queries", summary.get("total_queries", 0))
    metric_columns[1].metric("Users", summary.get("unique_users", 0))
    metric_columns[2].metric("Avg latency", f"{summary.get('avg_latency_ms', 0)} ms")
    metric_columns[3].metric("Max latency", f"{summary.get('max_latency_ms', 0)} ms")
    metric_columns[4].metric("Avg tokens", summary.get("avg_total_tokens", 0))
    metric_columns[5].metric("Avg sources", f"{float(summary.get('avg_sources_per_query', 0)):.1f}")
    metric_columns[6].metric("Avg faithfulness", format_score(ragas_summary.get("ragas_faithfulness")))
    metric_columns[7].metric("Guardrails", summary.get("guardrail_trigger_count", 0))

    st.divider()
    chart_columns = st.columns(4)
    tool_rows = count_rows(summary.get("tool_flow_counts") or summary.get("tool_counts") or {}, "Tool")
    agent_summary_rows = count_rows(summary.get("agent_counts") or {}, "Agent")
    user_rows = count_rows(summary.get("user_counts") or {}, "User")
    model_rows = count_rows(summary.get("model_counts") or {}, "Model")
    with chart_columns[0]:
        st.subheader("Tool flow")
        if tool_rows:
            st.bar_chart(tool_rows, x="Tool", y="Count")
        else:
            st.caption("No tool calls yet")
    with chart_columns[1]:
        st.subheader("Agents")
        if agent_summary_rows:
            st.bar_chart(agent_summary_rows, x="Agent", y="Count")
        else:
            st.caption("No agent flow yet")
    with chart_columns[2]:
        st.subheader("Users")
        if user_rows:
            st.bar_chart(user_rows, x="User", y="Count")
        else:
            st.caption("No user activity yet")
    with chart_columns[3]:
        st.subheader("Models")
        if model_rows:
            st.bar_chart(model_rows, x="Model", y="Count")
        else:
            st.caption("No model activity yet")

    st.divider()
    st.subheader("Per-query details")
    query_rows = []
    for item in queries:
        query_rows.append(
            {
                "Time": item.get("created_at", ""),
                "User": item.get("user_id", ""),
                "Query": item.get("query", ""),
                "Model": item.get("model", ""),
                "Sources": item.get("source_count", 0),
                "Tokens": item.get("total_tokens", 0),
                "Latency ms": item.get("latency_ms", 0),
                "Guardrail": "Yes" if item.get("guardrail_applied") else "No",
            }
        )
    if query_rows:
        st.caption("Click a row to open query details.")
        table_event = st.dataframe(
            query_rows,
            hide_index=True,
            use_container_width=True,
            height=430,
            on_select="rerun",
            selection_mode="single-row",
            column_order=[
                "Time",
                "User",
                "Query",
                "Model",
                "Sources",
                "Tokens",
                "Latency ms",
                "Guardrail",
            ],
            column_config={
                "Time": st.column_config.TextColumn("Time", width="medium"),
                "User": st.column_config.TextColumn("User", width="small"),
                "Query": st.column_config.TextColumn("Query", width="large"),
                "Model": st.column_config.TextColumn("Model", width="small"),
                "Sources": st.column_config.NumberColumn("Sources", width="small"),
                "Tokens": st.column_config.NumberColumn("Tokens", width="small"),
                "Latency ms": st.column_config.NumberColumn("Latency ms", width="small"),
                "Guardrail": st.column_config.TextColumn("Guardrail", width="small"),
            },
        )
        selected_rows = []
        try:
            selected_rows = list(table_event.selection.rows)
        except Exception:
            selected_rows = []
        if selected_rows:
            selected_index = int(selected_rows[0])
            if 0 <= selected_index < len(queries):
                selected_item = queries[selected_index]
                if hasattr(st, "dialog"):

                    @st.dialog("Query details", width="large")
                    def query_detail_dialog() -> None:
                        render_query_detail(selected_item)

                    query_detail_dialog()
                else:
                    st.markdown("**Selected query details**")
                    render_query_detail(selected_item)
    else:
        st.info("No chat queries found yet.")


CRM_SECTION_LABELS = {
    "patients": "Patients",
    "doctors": "Doctors",
    "departments": "Departments",
    "schedule": "Schedule",
    "appointments": "Appointments",
    "finance": "Finance",
    "wards": "Wards",
    "contacts": "Contacts",
    "formulary": "Formulary",
    "clinic_sessions": "Clinic Sessions",
    "equipment": "Equipment",
    "compliance_audits": "Compliance Audits",
    "training": "Training",
}

CRM_PRIMARY_SECTIONS = (
    "patients",
    "doctors",
    "departments",
    "schedule",
    "appointments",
    "finance",
)


CRM_FIELD_LABELS = {
    "access_level": "Access level",
    "account_type": "Account type",
    "amount_due": "Amount due",
    "amount_paid": "Amount paid",
    "appointment_date": "Appointment date",
    "appointment_id": "Appointment ID",
    "appointment_time": "Appointment time",
    "balance": "Balance",
    "bleep": "Bleep",
    "care_status": "Care status",
    "clinic_date": "Clinic date",
    "clinic_name": "Clinic",
    "clinic_id": "Clinic ID",
    "clinician_name": "Clinician",
    "clinical_engineering_contact": "Clinical engineering contact",
    "completion_date": "Completion date",
    "contact": "Contact",
    "contact_id": "Contact ID",
    "contact_name": "Contact name",
    "contact_type": "Contact type",
    "date_of_birth": "Date of birth",
    "department_id": "Department ID",
    "department_name": "Department",
    "doctor_id": "Doctor ID",
    "email": "Email",
    "equipment_type": "Equipment type",
    "escalation_level": "Escalation level",
    "finance_id": "Finance ID",
    "full_name": "Name",
    "grade": "Grade",
    "invoice_status": "Invoice status",
    "last_score_percent": "Last score",
    "last_service_date": "Last service date",
    "lead": "Lead",
    "last_invoice_date": "Last invoice date",
    "main_phone": "Main phone",
    "max_adult_dose": "Max adult dose",
    "medicine_id": "Medicine ID",
    "medicine_name": "Medicine",
    "training_module": "Training module",
    "next_service_due": "Next service due",
    "mrn": "MRN",
    "named_consultant": "Named consultant",
    "nhs_number": "NHS number",
    "on_call_today": "On call today",
    "on_call": "On call",
    "patient_id": "Patient ID",
    "patient_mrn": "Patient MRN",
    "patient_name": "Patient name",
    "payer_type": "Payer type",
    "phone": "Phone",
    "referral_priority": "Referral priority",
    "restricted": "Restricted",
    "risk_flags": "Risk flags",
    "role": "Role",
    "schedule_id": "Schedule ID",
    "service_lead": "Service lead",
    "expiry_date": "Expiry date",
    "shift_date": "Shift date",
    "shift_end": "Shift end",
    "shift_start": "Shift start",
    "slots_available": "Slots available",
    "slots_total": "Slots total",
    "specialty": "Specialty",
    "specialty_group": "Specialty group",
    "staff_name": "Staff name",
    "status": "Status",
    "topic": "Topic",
    "training_id": "Training ID",
    "ward_code": "Ward",
    "ward_name": "Ward name",
}


def crm_label(value: str) -> str:
    return CRM_FIELD_LABELS.get(value, value.replace("_", " ").title())


def widget_key_part(value: Any) -> str:
    return "".join(character if character.isalnum() else "_" for character in str(value or "item"))[:80]


def render_record_details(record: dict[str, Any], *, labeler=crm_label) -> None:
    detail_rows = [
        {"Field": labeler(str(key)), "Value": "" if value is None else str(value)}
        for key, value in record.items()
        if value not in (None, "")
    ]
    if detail_rows:
        st.dataframe(detail_rows, hide_index=True, use_container_width=True)
    else:
        st.caption("No details available for this record.")


def crm_filter_controls(section: str, filters: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    if not filters:
        return values
    columns = st.columns(min(len(filters), 4))
    for index, field in enumerate(filters):
        values[field] = columns[index % len(columns)].text_input(crm_label(field), key=f"crm-filter-{section}-{field}")
    return values


def crm_payload_form(
    section: str,
    columns: list[str],
    defaults: dict[str, Any] | None = None,
    *,
    disabled_pk: str = "",
    key_suffix: str = "",
) -> dict[str, Any]:
    defaults = defaults or {}
    payload: dict[str, Any] = {}
    field_columns = st.columns(3)
    for index, column in enumerate(columns):
        value = defaults.get(column, "")
        label = crm_label(column)
        disabled = bool(disabled_pk and column == disabled_pk)
        widget_key = f"crm-{section}-{column}-{widget_key_part(key_suffix or disabled_pk or 'new')}"
        if column in {"on_call", "on_call_today", "restricted"}:
            payload[column] = field_columns[index % 3].checkbox(
                label,
                value=bool(value),
                disabled=disabled,
                key=widget_key,
            )
        else:
            payload[column] = field_columns[index % 3].text_input(
                label,
                value="" if value is None else str(value),
                disabled=disabled,
                key=widget_key,
            )
    return payload


def render_hospital_crm_dashboard(section: str) -> None:
    label = CRM_SECTION_LABELS.get(section, section.title())
    render_page_title(f"Hospital CRM - {label}")
    try:
        sections = get_json("/admin/crm/sections")
        section_meta = dict(sections).get(section, {}) if isinstance(sections, dict) else {}
    except Exception as exc:
        st.error(f"Unable to load CRM metadata: {exc}")
        return

    columns = list(section_meta.get("columns") or [])
    primary_key = str(section_meta.get("primary_key") or (columns[0] if columns else "id"))
    filters = list(section_meta.get("filters") or [])

    with st.form(f"crm-filters-{section}"):
        top = st.columns([3, 1])
        search = top[0].text_input("Search", placeholder=f"Search {label.lower()}")
        limit = top[1].number_input("Limit", min_value=1, max_value=500, value=100, step=25)
        filter_values = crm_filter_controls(section, filters)
        submitted = st.form_submit_button("Apply filters")

    cache_key = f"crm_payload_{section}"
    error_key = f"crm_error_{section}"
    if submitted or cache_key not in st.session_state:
        params = {"q": search, "limit": int(limit)}
        params.update({key: value for key, value in filter_values.items() if value})
        try:
            payload = get_json(f"/admin/crm/{section}", params=params)
            st.session_state[cache_key] = payload if isinstance(payload, dict) else {}
            st.session_state[error_key] = None
        except Exception as exc:
            st.session_state[cache_key] = {}
            st.session_state[error_key] = str(exc)

    if st.session_state.get(error_key):
        st.error(f"Unable to load {label.lower()}: {st.session_state[error_key]}")
        return

    payload = st.session_state.get(cache_key) or {}
    rows = list(payload.get("rows") or [])
    summary = payload.get("summary") or {}
    metric_columns = st.columns(3)
    metric_columns[0].metric("Rows", summary.get("row_count", len(rows)))
    metric_columns[1].metric("Section", label)
    metric_columns[2].metric("Primary key", primary_key)

    def render_crm_record_overlay(selected_row: dict[str, Any]) -> None:
        selected_id = str(selected_row.get(primary_key) or "")
        render_record_details(selected_row)
        st.divider()
        with st.expander("Edit record", expanded=True):
            with st.form(f"crm-update-{section}-{widget_key_part(selected_id)}"):
                update_payload = crm_payload_form(
                    section,
                    columns,
                    selected_row,
                    disabled_pk=primary_key,
                    key_suffix=selected_id,
                )
                update_submitted = st.form_submit_button("Save changes")
            if update_submitted:
                try:
                    patch_json(f"/admin/crm/{section}/{selected_id}", update_payload)
                    st.session_state.pop(cache_key, None)
                    st.success("Record updated")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Update failed: {exc}")
        with st.expander("Delete record", expanded=False):
            st.warning(f"Delete {selected_id} from {label}.")
            confirm_delete = st.checkbox(
                "I understand this will delete the selected record",
                key=f"crm-delete-confirm-{section}-{widget_key_part(selected_id)}",
            )
            if st.button(
                "Delete record",
                key=f"crm-delete-{section}-{widget_key_part(selected_id)}",
                disabled=not confirm_delete,
            ):
                try:
                    delete_json(f"/admin/crm/{section}/{selected_id}")
                    st.session_state.pop(cache_key, None)
                    st.success("Record deleted")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Delete failed: {exc}")

    if rows:
        st.caption("Click a row to view, edit, or delete the record.")
        table_event = st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True,
            height=620,
            on_select="rerun",
            selection_mode="single-row",
        )
        selected_rows = []
        try:
            selected_rows = list(table_event.selection.rows)
        except Exception:
            selected_rows = []
        if selected_rows:
            selected_index = int(selected_rows[0])
            if 0 <= selected_index < len(rows):
                selected_row = rows[selected_index]
                selected_title = str(selected_row.get(primary_key) or label)
                if hasattr(st, "dialog"):

                    @st.dialog(f"{label} record", width="large")
                    def crm_record_dialog() -> None:
                        st.subheader(selected_title)
                        render_crm_record_overlay(selected_row)

                    crm_record_dialog()
                else:
                    st.subheader(selected_title)
                    render_crm_record_overlay(selected_row)
    else:
        st.info(summary.get("message") or f"No {label.lower()} records found.")

    with st.expander(f"Create {label[:-1] if label.endswith('s') else label}"):
        with st.form(f"crm-create-{section}"):
            create_payload = crm_payload_form(section, columns)
            create_submitted = st.form_submit_button("Create / upsert")
        if create_submitted:
            try:
                post_json(f"/admin/crm/{section}", create_payload)
                st.session_state.pop(cache_key, None)
                st.success("Record saved")
                st.rerun()
            except Exception as exc:
                st.error(f"Create failed: {exc}")


def document_table_rows(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for document in documents:
        metadata = document.get("metadata") or {}
        key = document.get("key") or str(document.get("uri", "")).split("/", 3)[-1]
        roles = metadata.get("allowed_roles") or []
        if isinstance(roles, str):
            roles = [roles]
        rows.append(
            {
                "File": document.get("title") or str(key).rsplit("/", 1)[-1],
                "Chunks": document.get("chunk_count", 0),
                "Category": metadata.get("domain", "general"),
                "Type": metadata.get("document_type", "document"),
                "Access roles": ", ".join(str(role) for role in roles),
                "Status": document.get("ingestion_status") or "indexed",
                "URI": document.get("uri", ""),
            }
        )
    return rows


def _document_roles_display(roles: Any) -> str:
    if isinstance(roles, str):
        raw_roles = [role.strip() for role in roles.split(",")]
    elif isinstance(roles, list):
        raw_roles = [str(role).strip() for role in roles]
    else:
        raw_roles = []
    return ", ".join(role for role in raw_roles if role)


def _parse_document_roles(value: Any) -> list[str]:
    roles = [role.strip() for role in str(value or "").split(",") if role.strip()]
    valid_roles = [role for role in roles if role in KNOWN_ROLES]
    return valid_roles or ["staff"]


def _metadata_options(options: list[str], current_value: str) -> list[str]:
    value = (current_value or "").strip()
    if value and value not in options:
        return [value, *options]
    return list(options)


def _option_index(options: list[str], current_value: str, default: str) -> int:
    value = current_value if current_value in options else default
    try:
        return options.index(value)
    except ValueError:
        return 0


def _update_cached_document(updated_document: dict[str, Any]) -> None:
    updated_key = updated_document.get("key")
    documents = []
    replaced = False
    for document in st.session_state.get("document_cache", []):
        if document.get("key") == updated_key:
            documents.append(updated_document)
            replaced = True
        else:
            documents.append(document)
    if not replaced:
        documents.append(updated_document)
    st.session_state.document_cache = documents
    st.session_state.document_cache_loaded = True
    st.session_state.document_cache_error = None


def document_detail_label(value: str) -> str:
    labels = {
        "title": "Title",
        "key": "Key",
        "uri": "URI",
        "content_type": "Content type",
        "chunk_count": "Chunks",
        "ingestion_status": "Status",
        "domain": "Category",
        "document_type": "Document type",
        "allowed_roles": "Access roles",
    }
    return labels.get(value, value.replace("_", " ").title())


def _remove_cached_document(document_key: str) -> None:
    st.session_state.document_cache = [
        document
        for document in st.session_state.get("document_cache", [])
        if str(document.get("key") or "") != document_key
    ]
    st.session_state.document_cache_loaded = True
    st.session_state.document_cache_error = None


def _bulk_document_metadata_rows(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in documents:
        metadata = document.get("metadata") or {}
        key = str(document.get("key") or document.get("uri") or document.get("title") or "")
        rows.append(
            {
                "Key": key,
                "File": document.get("title") or key.rsplit("/", 1)[-1],
                "Category": str(metadata.get("domain") or "general"),
                "Document type": str(metadata.get("document_type") or "document"),
                "Access roles": _document_roles_display(metadata.get("allowed_roles") or ["staff"]),
            }
        )
    return rows


def _edited_rows_to_records(edited_rows: Any) -> list[dict[str, Any]]:
    if hasattr(edited_rows, "to_dict"):
        try:
            return list(edited_rows.to_dict("records"))
        except Exception:
            return []
    if isinstance(edited_rows, list):
        return [dict(row) for row in edited_rows if isinstance(row, dict)]
    return []


def render_bulk_document_metadata_overlay(documents: list[dict[str, Any]]) -> None:
    if not documents:
        st.info("No documents are available to edit.")
        return

    original_rows = _bulk_document_metadata_rows(documents)
    category_options = sorted(
        set(DOCUMENT_CATEGORY_OPTIONS)
        | {str(row.get("Category") or "general") for row in original_rows if str(row.get("Category") or "").strip()}
    )
    type_options = sorted(
        set(DOCUMENT_TYPE_OPTIONS)
        | {
            str(row.get("Document type") or "document")
            for row in original_rows
            if str(row.get("Document type") or "").strip()
        }
    )
    role_options = list(DOCUMENT_ACCESS_ROLE_PRESETS)
    for row in original_rows:
        roles = str(row.get("Access roles") or "").strip()
        if roles and roles not in role_options:
            role_options.append(roles)

    st.caption("Edit metadata for all visible documents. Changes are saved to the manifest metadata.")
    edited_rows = st.data_editor(
        original_rows,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        disabled=["Key", "File"],
        column_order=["File", "Category", "Document type", "Access roles", "Key"],
        column_config={
            "File": st.column_config.TextColumn("File", width="large"),
            "Category": st.column_config.SelectboxColumn("Category", options=category_options, required=True),
            "Document type": st.column_config.SelectboxColumn("Document type", options=type_options, required=True),
            "Access roles": st.column_config.SelectboxColumn("Access roles", options=role_options, required=True),
            "Key": st.column_config.TextColumn("Key", width="medium"),
        },
        key="bulk-document-metadata-editor",
    )
    if st.button("Save all metadata changes", type="primary"):
        original_by_key = {str(row.get("Key") or ""): row for row in original_rows}
        changed_rows = []
        for row in _edited_rows_to_records(edited_rows):
            key = str(row.get("Key") or "")
            original = original_by_key.get(key)
            if not key or not original:
                continue
            if (
                str(row.get("Category") or "") != str(original.get("Category") or "")
                or str(row.get("Document type") or "") != str(original.get("Document type") or "")
                or str(row.get("Access roles") or "") != str(original.get("Access roles") or "")
            ):
                changed_rows.append(row)

        if not changed_rows:
            st.info("No metadata changes to save.")
            return

        progress = st.progress(0, text="Saving metadata changes...")
        saved = 0
        try:
            for index, row in enumerate(changed_rows, start=1):
                updated = patch_json(
                    "/admin/documents/metadata",
                    {
                        "key": str(row.get("Key") or ""),
                        "category": str(row.get("Category") or "general"),
                        "document_type": str(row.get("Document type") or "document"),
                        "allowed_roles": _parse_document_roles(row.get("Access roles")),
                    },
                )
                _update_cached_document(updated)
                saved += 1
                progress.progress(index / len(changed_rows), text=f"Saved {index} of {len(changed_rows)} document(s)")
            st.session_state.document_metadata_notice = (
                f"Updated metadata for {saved} document(s). Run ingestion to apply changes to indexed chunks."
            )
            st.rerun()
        except Exception as exc:
            progress.empty()
            st.error(f"Bulk metadata update failed after {saved} document(s): {exc}")


def run_document_ingestion_with_progress(*, initial_label: str = "Preparing ingestion...") -> dict[str, Any]:
    progress = st.progress(0, text=initial_label)
    progress.progress(0.15, text="Reading uploaded source files...")
    progress.progress(0.35, text="Parsing documents and preserving existing metadata...")
    progress.progress(0.55, text="Indexing chunks in the search backend...")
    result = post_json("/admin/documents/ingest", {})
    progress.progress(0.9, text="Refreshing document manifest...")
    st.session_state.document_cache = list(result.get("documents", []))
    st.session_state.document_cache_loaded = True
    st.session_state.document_cache_error = None
    progress.progress(1.0, text="Ingestion and indexing complete.")
    return result


def render_document_detail_overlay(document: dict[str, Any], *, index: int) -> None:
    metadata = document.get("metadata") or {}
    title = document.get("title") or document.get("key") or document.get("uri") or "Untitled"
    document_key = str(document.get("key") or document.get("uri") or title)
    current_category = str(metadata.get("domain") or "general")
    current_type = str(metadata.get("document_type") or "document")
    raw_roles = metadata.get("allowed_roles", [])
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    current_roles = [role for role in raw_roles if role in KNOWN_ROLES]
    detail_payload = {
        "title": title,
        "key": document.get("key", ""),
        "uri": document.get("uri", ""),
        "content_type": document.get("content_type", ""),
        "chunk_count": document.get("chunk_count", 0),
        "ingestion_status": document.get("ingestion_status") or "indexed",
        "domain": current_category,
        "document_type": current_type,
        "allowed_roles": ", ".join(str(role) for role in raw_roles),
    }
    render_record_details(detail_payload, labeler=document_detail_label)

    category_options = _metadata_options(DOCUMENT_CATEGORY_OPTIONS, current_category)
    type_options = _metadata_options(DOCUMENT_TYPE_OPTIONS, current_type)
    key_part = widget_key_part(f"{index}-{document_key}")
    st.divider()
    with st.expander("Edit metadata", expanded=True):
        with st.form(f"document-metadata-{key_part}"):
            category = st.selectbox(
                "Category",
                category_options,
                index=_option_index(category_options, current_category, "general"),
            )
            document_type = st.selectbox(
                "Document type",
                type_options,
                index=_option_index(type_options, current_type, "document"),
            )
            allowed_roles = st.multiselect(
                "Access roles",
                KNOWN_ROLES,
                default=current_roles or ["staff"],
            )
            submitted = st.form_submit_button("Save metadata")
        if submitted:
            if not allowed_roles:
                st.error("Select at least one access role")
            else:
                try:
                    updated = patch_json(
                        "/admin/documents/metadata",
                        {
                            "key": document_key,
                            "category": category,
                            "document_type": document_type,
                            "allowed_roles": allowed_roles,
                        },
                    )
                    _update_cached_document(updated)
                    st.session_state.document_metadata_notice = (
                        "Document metadata updated. Run ingestion to apply metadata changes to indexed search chunks."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Metadata update failed: {exc}")

    with st.expander("Delete document", expanded=False):
        st.warning("This removes the document from the admin manifest and deletes the uploaded source file where available.")
        confirm_delete = st.checkbox(
            "I understand this will delete the selected document",
            key=f"document-delete-confirm-{key_part}",
        )
        if st.button("Delete document", key=f"document-delete-{key_part}", disabled=not confirm_delete):
            try:
                delete_json(f"/admin/documents/{quote(document_key, safe='')}")
                _remove_cached_document(str(document.get("key") or ""))
                st.session_state.document_metadata_notice = "Document deleted. Run ingestion to refresh indexed chunks."
                st.rerun()
            except Exception as exc:
                st.error(f"Document delete failed: {exc}")

def render_documents_table(documents: list[dict[str, Any]]) -> None:
    rows = document_table_rows(documents)
    st.subheader("Indexed documents")
    if not rows:
        st.info("No indexed documents found. Upload files and run ingestion to create searchable chunks.")
        return
    metric_columns = st.columns(3)
    metric_columns[0].metric("Documents", len(rows))
    metric_columns[1].metric("Total chunks", sum(int(row.get("Chunks") or 0) for row in rows))
    metric_columns[2].metric(
        "Categories",
        len({str(row.get("Category") or "general") for row in rows}),
    )
    st.caption("Click a row to view, edit, or delete the document.")
    table_event = st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
        height=560,
        on_select="rerun",
        selection_mode="single-row",
        column_order=["File", "Chunks", "Category", "Type", "Access roles", "Status", "URI"],
        column_config={
            "File": st.column_config.TextColumn("File", width="large"),
            "Chunks": st.column_config.NumberColumn("Chunks", width="small"),
            "Category": st.column_config.TextColumn("Category", width="medium"),
            "Type": st.column_config.TextColumn("Type", width="medium"),
            "Access roles": st.column_config.TextColumn("Access roles", width="medium"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "URI": st.column_config.TextColumn("URI", width="medium"),
        },
    )
    selected_rows = []
    try:
        selected_rows = list(table_event.selection.rows)
    except Exception:
        selected_rows = []
    if selected_rows:
        selected_index = int(selected_rows[0])
        if 0 <= selected_index < len(documents):
            selected_document = documents[selected_index]
            selected_title = str(selected_document.get("title") or selected_document.get("key") or "Document")
            if hasattr(st, "dialog"):

                @st.dialog("Document details", width="large")
                def document_detail_dialog() -> None:
                    st.subheader(selected_title)
                    render_document_detail_overlay(selected_document, index=selected_index)

                document_detail_dialog()
            else:
                st.subheader(selected_title)
                render_document_detail_overlay(selected_document, index=selected_index)

    if st.button("Edit all document metadata", key="edit-all-document-metadata"):
        if hasattr(st, "dialog"):

            @st.dialog("Edit all document metadata", width="large")
            def bulk_document_metadata_dialog() -> None:
                render_bulk_document_metadata_overlay(documents)

            bulk_document_metadata_dialog()
        else:
            st.subheader("Edit all document metadata")
            render_bulk_document_metadata_overlay(documents)


def render_admin_documents() -> None:
    render_page_title("Documents")
    current_documents: list[dict[str, Any]] = list(st.session_state.get("document_cache", []))
    if not st.session_state.get("document_cache_loaded"):
        warm_document_manifest_cache()
        current_documents = list(st.session_state.get("document_cache", []))
    if st.session_state.get("document_cache_error"):
        st.error(f"Unable to load indexed documents: {st.session_state.document_cache_error}")
    document_metadata_notice = st.session_state.pop("document_metadata_notice", None)
    if document_metadata_notice:
        st.success(document_metadata_notice)

    uploaded_files = st.file_uploader(
        "Upload documents to S3",
        type=["pdf", "docx", "txt", "md", "csv"],
        accept_multiple_files=True,
    )
    if st.button("Upload selected files", disabled=not uploaded_files):
        uploaded_count = 0
        upload_progress = st.progress(0, text="Starting upload...")
        selected_files = list(uploaded_files or [])
        for index, uploaded_file in enumerate(selected_files, start=1):
            try:
                upload_progress.progress(
                    (index - 1) / max(len(selected_files), 1),
                    text=f"Uploading {uploaded_file.name}...",
                )
                result = post_file(
                    "/admin/documents/upload",
                    "file",
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    uploaded_file.type or "application/octet-stream",
                )
                uploaded_count += 1
                st.caption(f"Uploaded {result['key']}")
                upload_progress.progress(
                    index / max(len(selected_files), 1),
                    text=f"Uploaded {index} of {len(selected_files)} file(s)",
                )
            except Exception as exc:
                st.error(f"Upload failed for {uploaded_file.name}: {exc}")
        if uploaded_count:
            st.success(f"Uploaded {uploaded_count} file(s). Indexing uploaded content...")
            try:
                result = run_document_ingestion_with_progress(initial_label="Starting indexing for uploaded files...")
                current_documents = list(result.get("documents", []))
                st.success("Upload and indexing complete")
            except Exception as exc:
                st.error(f"Indexing after upload failed: {exc}")

    st.divider()
    if st.button("Refresh indexed documents"):
        warm_document_manifest_cache()
        st.rerun()
    render_documents_table(current_documents)
    st.divider()
    st.subheader("Ingest and index")
    if st.button("Run ingestion and indexing"):
        try:
            result = run_document_ingestion_with_progress(initial_label="Starting full document ingestion...")
            st.success("Ingestion complete")
            metric_columns = st.columns(5)
            metric_columns[0].metric("Documents", len(result.get("documents", [])))
            metric_columns[1].metric("New chunks", result.get("indexed_chunks", 0))
            metric_columns[2].metric("Total chunks", result.get("total_chunks", 0))
            metric_columns[3].metric("Skipped", result.get("skipped_documents", 0))
            metric_columns[4].metric("Removed", result.get("deleted_documents", 0))
            if result.get("force_reindex"):
                st.caption(
                    "Re-indexed unchanged files because the OpenSearch index changed "
                    f"from {result.get('previous_opensearch_index') or 'unknown'} "
                    f"to {result.get('opensearch_index') or 'current index'}."
                )
            if result.get("deleted_chunks"):
                st.caption(f"Deleted {result.get('deleted_chunks')} stale indexed chunk(s)")
        except Exception as exc:
            st.error(f"Ingestion failed: {exc}")

    st.divider()
    with st.expander("Delete all indexes"):
        st.warning(
            "This clears search/vector indexes and the document manifest. "
            "Uploaded source files are preserved, but deterministic Postgres CSV lookup rows are deleted."
        )
        with st.form("delete-all-indexes"):
            admin_password = st.text_input("Admin password", type="password")
            confirm_delete = st.checkbox("I understand this will clear all indexed document entries")
            delete_submitted = st.form_submit_button("Delete all indexes")
        if delete_submitted:
            if not admin_password:
                st.error("Enter your admin password")
                return
            if not confirm_delete:
                st.error("Confirm that you understand the index entries will be cleared")
                return
            try:
                result = post_json(
                    "/admin/documents/delete-indexes",
                    {"admin_password": admin_password},
                )
                st.success(
                    f"Deleted {result.get('deleted_chunks', 0)} indexed chunk(s) "
                    f"from {result.get('backend', 'search')}, deleted "
                    f"{result.get('deleted_lookup_rows', 0)} CSV lookup row(s), and cleared the manifest."
                )
                st.session_state.document_cache = []
                st.session_state.document_cache_loaded = True
                st.session_state.document_cache_error = None
                st.rerun()
            except Exception as exc:
                st.error(f"Delete indexes failed: {exc}")


def format_score(value: Any) -> str:
    try:
        if value is None:
            return "-"
        return f"{float(value):.2f}"
    except Exception:
        return "-"


def submit_chat_query(query: str) -> None:
    payload = {
        "query": query,
        "session_id": st.session_state.get("session_id"),
    }
    data = post_json("/chat", payload)
    st.session_state.session_id = data["session_id"]
    st.session_state.messages.append({"role": "assistant", "content": data["answer"]})


def _query_has_any(query: str, markers: list[str]) -> bool:
    lowered = query.lower()
    return any(marker in lowered for marker in markers)


def chat_progress_steps(query: str) -> list[dict[str, str]]:
    lowered = query.lower()
    is_multipart = bool(re.search(r"\b(and|also|plus)\b|[?].+\S", lowered))
    steps: list[dict[str, str]] = [
        {
            "label": "Read and route the request",
            "agent": "SupervisorAgent",
            "tool": "supervisor",
            "detail": (
                "Checking intent and splitting the question into parts so each part can use the right specialist."
                if is_multipart
                else "Checking intent so the request can use the right specialist."
            ),
        }
    ]

    planned = False
    if _query_has_any(
        lowered,
        [
            "on call",
            "on-call",
            "oncall",
            "rota",
            "shift",
            "appointment",
            "patient",
            "ward",
            "equipment",
            "ventilator",
            "defibrillator",
            "asset",
            "device",
            "medicine",
            "drug",
            "formulary",
            "contact",
            "doctor",
            "department",
            "finance",
            "training",
        ],
    ):
        steps.append(
            {
                "label": "Check operational tables",
                "agent": "DeterministicLookupAgent",
                "tool": "postgres_deterministic_lookup",
                "detail": "Looking up exact facts in Postgres tables such as rota, patients, appointments, contacts, equipment, and formulary.",
            }
        )
        planned = True

    catalog_intent = (
        _query_has_any(lowered, ["catalog", "catalogue", "uploaded", "indexed", "document list", "available documents"])
        or (
            "document" in lowered
            and _query_has_any(lowered, ["which", "list", "do we have", "we have", "available"])
        )
    )
    policy_content_intent = (
        not catalog_intent
        or _query_has_any(
            lowered,
            ["what does", "how", "explain", "summar", "procedure", "apply", "handle", "report", "stored", "retention"],
        )
    )

    if policy_content_intent and _query_has_any(
        lowered,
        [
            "policy",
            "policies",
            "sop",
            "guideline",
            "guidelines",
            "pathway",
            "retention",
            "stored",
            "records management",
            "privacy",
            "governance",
            "confidentiality",
            "research",
            "incident",
            "compliance",
        ],
    ):
        steps.append(
            {
                "label": "Search policy evidence",
                "agent": "PolicyAgent",
                "tool": "policy_search",
                "detail": "Searching indexed policy, SOP, guideline, governance, and compliance evidence for a supported answer.",
            }
        )
        planned = True

    if catalog_intent:
        steps.append(
            {
                "label": "Check document catalog",
                "agent": "CatalogAgent",
                "tool": "catalogue_search",
                "detail": "Checking available document and table metadata so inventory questions return the right assets.",
            }
        )
        planned = True

    if _query_has_any(lowered, ["urgent", "quick", "emergency", "unsafe", "escalate", "risk", "safeguarding", "safety"]):
        steps.append(
            {
                "label": "Review safety context",
                "agent": "SafetyAgent",
                "tool": "safety_guard",
                "detail": "Checking whether the answer should include escalation or safety guidance.",
            }
        )
        planned = True

    if not planned:
        steps.append(
            {
                "label": "Search indexed knowledge",
                "agent": "RAGAgent",
                "tool": "rag_search",
                "detail": "Searching indexed document chunks for relevant context.",
            }
        )

    if any(step["agent"] == "PolicyAgent" for step in steps):
        steps.append(
            {
                "label": "Broaden search if needed",
                "agent": "RAGAgent",
                "tool": "rag_search",
                "detail": "If focused policy evidence is thin, broader document retrieval may add supporting context.",
            }
        )

    steps.append(
        {
            "label": "Prepare final response",
            "agent": "SynthesisAgent",
            "tool": "synthesis",
            "detail": "Combining the specialist evidence into a concise answer with sources where available.",
        }
    )
    return steps


def _chat_request_worker(
    query: str,
    session_id: str | None,
    headers: dict[str, str],
    result_queue: "queue.Queue[tuple[str, Any]]",
) -> None:
    try:
        response = requests.post(
            f"{BACKEND_URL}/chat",
            json={"query": query, "session_id": session_id},
            headers=headers,
            timeout=300,
        )
        raise_for_api_error(response)
        result_queue.put(("ok", response.json()))
    except Exception as exc:
        result_queue.put(("error", exc))


def render_chat_progress(
    progress_placeholder: Any,
    steps: list[dict[str, str]],
    active_index: int,
    *,
    label: str = "Working on your question...",
    state: str = "running",
) -> None:
    with progress_placeholder.container():
        with st.chat_message("assistant"):
            with st.status(label, expanded=True, state=state):
                st.markdown("**What is being done**")
                for index, step in enumerate(steps):
                    if index < active_index:
                        status_label = "Done"
                    elif index == active_index:
                        status_label = "In progress"
                    else:
                        status_label = "Queued"
                    st.markdown(
                        f"**{status_label}: {step['label']}**  \n"
                        f"{step['agent']} / {step['tool']} - {step['detail']}"
                    )
    scroll_chat_to_latest()


def submit_chat_query_with_progress(query: str, progress_placeholder: Any) -> None:
    result_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue(maxsize=1)
    headers = api_headers()
    worker = threading.Thread(
        target=_chat_request_worker,
        args=(query, st.session_state.get("session_id"), headers, result_queue),
        daemon=True,
    )
    worker.start()

    step_index = 0
    progress_steps = chat_progress_steps(query)
    render_chat_progress(progress_placeholder, progress_steps, step_index)
    while worker.is_alive():
        worker.join(timeout=0.75)
        if not worker.is_alive():
            break
        step_index = min(step_index + 1, len(progress_steps) - 1)
        render_chat_progress(progress_placeholder, progress_steps, step_index)
    render_chat_progress(
        progress_placeholder,
        progress_steps,
        len(progress_steps),
        label="Answer ready.",
        state="complete",
    )

    state, payload = result_queue.get()
    if state == "error":
        progress_placeholder.empty()
        raise payload
    progress_placeholder.empty()
    st.session_state.session_id = payload["session_id"]
    st.session_state.messages.append({"role": "assistant", "content": payload["answer"]})


def render_chat_messages() -> Any:
    st.markdown('<span class="hka-chat-window-marker"></span>', unsafe_allow_html=True)
    messages = st.session_state.get("messages", [])
    if not messages:
        st.info("Ask a question about healthcare knowledge.")
    for message in messages:
        if message.get("role") == "notice":
            st.info(message.get("content", ""))
            continue
        role = "assistant" if message.get("role") == "assistant" else "user"
        with st.chat_message(role):
            st.markdown(message.get("content", ""), unsafe_allow_html=role == "assistant")
    progress_placeholder = st.empty()
    st.markdown('<span class="hka-chat-bottom-anchor"></span>', unsafe_allow_html=True)
    return progress_placeholder


def scroll_chat_to_latest() -> None:
    components.html(
        """
        <script>
        const scrollLatestChat = () => {
            const doc = window.parent.document;
            const anchors = Array.from(doc.querySelectorAll(".hka-chat-bottom-anchor"));
            const anchor = anchors[anchors.length - 1];
            const markers = Array.from(doc.querySelectorAll(".hka-chat-window-marker"));
            const marker = markers[markers.length - 1];
            if (!marker) return;
            const wrapper = marker.closest('div[data-testid="stVerticalBlockBorderWrapper"]');
            if (!wrapper) return;

            const candidates = [
                wrapper,
                wrapper.parentElement,
                ...Array.from(wrapper.querySelectorAll("div")),
                ...Array.from(wrapper.parentElement ? wrapper.parentElement.querySelectorAll("div") : []),
            ].filter(Boolean);
            const scrollables = candidates.filter((element) => {
                const style = window.parent.getComputedStyle(element);
                return element.scrollHeight > element.clientHeight + 4
                    && style.display !== "none"
                    && style.visibility !== "hidden";
            });
            for (const element of scrollables) {
                element.scrollTop = element.scrollHeight;
            }
            const target = anchor || wrapper.querySelector('[data-testid="stChatMessage"]:last-of-type') || marker;
            target.scrollIntoView({ block: "end", inline: "nearest" });
        };

        const installChatAutoScroll = () => {
            const doc = window.parent.document;
            const marker = Array.from(doc.querySelectorAll(".hka-chat-window-marker")).pop();
            if (!marker) return;
            const wrapper = marker.closest('div[data-testid="stVerticalBlockBorderWrapper"]');
            if (!wrapper) return;

            if (window.parent.__hkaChatScrollObserver) {
                window.parent.__hkaChatScrollObserver.disconnect();
            }
            window.parent.__hkaChatScrollObserver = new MutationObserver(() => scrollLatestChat());
            window.parent.__hkaChatScrollObserver.observe(wrapper, {
                childList: true,
                subtree: true,
                characterData: true,
            });
            setTimeout(() => {
                if (window.parent.__hkaChatScrollObserver) {
                    window.parent.__hkaChatScrollObserver.disconnect();
                    window.parent.__hkaChatScrollObserver = null;
                }
            }, 15000);
        };

        [0, 25, 75, 150, 350, 750, 1500, 2500].forEach((delay) => setTimeout(scrollLatestChat, delay));
        setTimeout(installChatAutoScroll, 25);
        </script>
        """,
        height=0,
    )


def render_chat_page() -> None:
    inject_chat_layout_css()
    st.markdown('<span class="hka-chat-page-marker"></span>', unsafe_allow_html=True)
    render_page_title("Chat")
    pending_query = st.session_state.pop("pending_chat_query", None)
    with st.container(height=620, border=True):
        if pending_query:
            st.session_state.setdefault("messages", []).append({"role": "user", "content": pending_query})
        progress_placeholder = render_chat_messages()
        if pending_query:
            scroll_chat_to_latest()
            try:
                submit_chat_query_with_progress(pending_query, progress_placeholder)
            except Exception as exc:
                st.error(f"Chat failed: {exc}")
                scroll_chat_to_latest()
                return
            scroll_chat_to_latest()
            st.rerun()
    query = st.chat_input("Ask a question about healthcare knowledge")
    if query and query.strip():
        st.session_state.pending_chat_query = query.strip()
        scroll_chat_to_latest()
        st.rerun()
    scroll_chat_to_latest()


def render_login_page() -> None:
    st.markdown(
        f"""
        <div class="hka-login-header">
            <div class="hka-login-title">{html.escape(APP_TITLE)}</div>
            <div class="hka-login-subtitle">
                Healthcare knowledge, documents, and NHS headlines in one workspace.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, login_column, right = st.columns([3, 2, 3])
    with login_column:
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        try:
            data = post_json("/auth/login", {"username": username, "password": password})
            store_login(data)
            warm_document_manifest_cache()
            st.session_state.session_id = None
            st.session_state.messages = []
            st.rerun()
        except Exception as exc:
            st.error(f"Login failed: {exc}")
    schedule_news_refresh()
    render_login_news_carousel()


def render_common_sidebar() -> None:
    st.caption(f"Signed in as {st.session_state.get('username') or 'user'}")
    if st.button("Sign out"):
        sign_out()


def render_chat_sidebar() -> None:
    if st.button("New chat"):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.rerun()

    try:
        sessions = get_json("/chat/sessions")
        if sessions:
            st.divider()
            st.caption("Previous chats")
            for session in sessions[:20]:
                label = session.get("title") or session["session_id"]
                if st.button(label, key=f"session-{session['session_id']}"):
                    detail = get_json(f"/chat/sessions/{session['session_id']}")
                    st.session_state.session_id = session["session_id"]
                    st.session_state.messages = detail.get("messages", [])
                    st.rerun()
    except Exception:
        st.caption("Chat history unavailable")


def render_password_change_page() -> None:
    with st.sidebar:
        render_common_sidebar()
    render_password_change()


def render_chat_app_page() -> None:
    with st.sidebar:
        render_common_sidebar()
        st.divider()
        render_chat_sidebar()
    render_manifest_status_overlay()
    render_chat_page()


def render_news_app_page() -> None:
    with st.sidebar:
        render_common_sidebar()
    render_manifest_status_overlay()
    render_news_page()


def render_dashboard_app_page() -> None:
    with st.sidebar:
        render_common_sidebar()
    render_manifest_status_overlay()
    render_admin_dashboard()


def render_patient_details_app_page() -> None:
    with st.sidebar:
        render_common_sidebar()
        st.divider()
        primary_labels = [CRM_SECTION_LABELS[key] for key in CRM_PRIMARY_SECTIONS]
        crm_section_label = st.radio(
            "CRM sections",
            primary_labels,
            index=0,
        )
        radio_section = next(
            key for key, value in CRM_SECTION_LABELS.items() if value == crm_section_label
        )
        try:
            available_sections = get_json("/admin/crm/sections")
        except Exception:
            available_sections = {}
        table_keys = [key for key in CRM_SECTION_LABELS if key in available_sections]
        if not table_keys:
            st.error("Unable to load CRM tables.")
            return
        if radio_section in table_keys:
            default_table_index = table_keys.index(radio_section)
        else:
            default_table_index = 0
        table_label = st.selectbox(
            "All tables",
            [CRM_SECTION_LABELS[key] for key in table_keys],
            index=default_table_index,
        )
    section = next(key for key in table_keys if CRM_SECTION_LABELS[key] == table_label)
    render_manifest_status_overlay()
    render_hospital_crm_dashboard(section)


def render_users_app_page() -> None:
    with st.sidebar:
        render_common_sidebar()
    render_manifest_status_overlay()
    render_admin_users()


def render_settings_app_page() -> None:
    with st.sidebar:
        render_common_sidebar()
    render_manifest_status_overlay()
    render_admin_settings()


def render_documents_app_page() -> None:
    with st.sidebar:
        render_common_sidebar()
    render_manifest_status_overlay()
    render_admin_documents()


st.set_page_config(page_title=APP_TITLE, page_icon=None, layout="wide")
inject_app_theme()
restore_login_from_cookie()
sync_auth_cookie()

if "access_token" not in st.session_state:
    pg = st.navigation(
        [st.Page(render_login_page, title="Sign in", icon=":material/login:", default=True)]
    )
elif st.session_state.get("password_change_required"):
    pg = st.navigation(
        [
            st.Page(
                render_password_change_page,
                title="Change password",
                icon=":material/password:",
                default=True,
            )
        ]
    )
elif "admin" in st.session_state.get("roles", []):
    pg = st.navigation(
        {
            "Main": [
                st.Page(render_chat_app_page, title="Chat", icon=":material/chat:", default=True),
                st.Page(render_news_app_page, title="News", icon=":material/newspaper:"),
            ],
            "Admin": [
                st.Page(render_dashboard_app_page, title="Dashboard", icon=":material/dashboard:"),
                st.Page(
                    render_patient_details_app_page,
                    title="Hospital CRM",
                    icon=":material/patient_list:",
                ),
                st.Page(render_users_app_page, title="Users", icon=":material/group:"),
                st.Page(render_documents_app_page, title="Documents", icon=":material/folder:"),
                st.Page(render_settings_app_page, title="Settings", icon=":material/settings:"),
            ],
        },
        position="sidebar",
    )
else:
    pg = st.navigation(
        [
            st.Page(render_chat_app_page, title="Chat", icon=":material/chat:", default=True),
            st.Page(render_news_app_page, title="News", icon=":material/newspaper:"),
        ]
    )

pg.run()

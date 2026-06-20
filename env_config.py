"""`.env` 파일을 open()으로 직접 읽어 API 키를 파싱합니다."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"

_PLACEHOLDER_FRAGMENTS = (
    "여기에",
    "api-키-입력",
    "your-api-key",
    "your_api_key",
    "insert-key",
    "paste-key",
)


def normalize_api_key(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.lstrip("\ufeff").strip().strip('"').strip("'")
    if not key.startswith("sk-ant-"):
        return None
    lowered = key.lower()
    if any(fragment in lowered for fragment in _PLACEHOLDER_FRAGMENTS):
        return None
    return key


def _read_env_lines() -> list[str]:
    if not ENV_FILE.is_file():
        return []
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            with ENV_FILE.open(encoding=encoding) as env_file:
                return env_file.readlines()
        except OSError:
            continue
    return []


def parse_env_file() -> dict[str, str]:
    """`.env` 파일을 open()으로 읽어 KEY=VALUE 형식을 파싱합니다."""
    values: dict[str, str] = {}
    for line in _read_env_lines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue

        name, _, raw_value = stripped.partition("=")
        name = name.lstrip("\ufeff").strip()
        value = raw_value.strip()
        if not value:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()

        values[name] = value.strip().strip('"').strip("'")
    return values


def get_anthropic_api_key() -> str | None:
    """`.env`, 환경변수, Streamlit Secrets에서 API 키를 반환합니다."""
    return normalize_api_key(_env_lookup("ANTHROPIC_API_KEY"))


def _env_lookup(name: str) -> str | None:
    values = parse_env_file()
    value = (values.get(name) or os.environ.get(name) or "").strip()
    if value:
        return value
    return _streamlit_secret(name)


def _streamlit_secret(name: str) -> str | None:
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()
        anthropic = st.secrets.get("anthropic")
        if anthropic and name == "ANTHROPIC_API_KEY":
            for key in ("api_key", "ANTHROPIC_API_KEY", "key"):
                if anthropic.get(key):
                    return str(anthropic[key]).strip()
        supabase = st.secrets.get("supabase")
        if supabase:
            alias = {
                "SUPABASE_URL": "url",
                "SUPABASE_ANON_KEY": "anon_key",
                "SUPABASE_KEY": "anon_key",
            }
            key = alias.get(name)
            if key and supabase.get(key):
                return str(supabase[key]).strip()
    except Exception:
        pass
    return None


def get_supabase_url() -> str | None:
    url = _env_lookup("SUPABASE_URL")
    return url or None


def get_supabase_anon_key() -> str | None:
    for name in ("SUPABASE_ANON_KEY", "SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        key = _env_lookup(name)
        if key:
            return key
    return None


def anthropic_config_status() -> dict[str, bool | str]:
    values = parse_env_file()
    raw = _env_lookup("ANTHROPIC_API_KEY")
    normalized = normalize_api_key(raw)
    return {
        "env_file_exists": ENV_FILE.is_file(),
        "raw_set": bool(raw),
        "key_valid": bool(normalized),
        "preview": api_key_preview(normalized),
        "found_in_env": "ANTHROPIC_API_KEY" in values,
    }


def supabase_config_status() -> dict[str, bool | str]:
    """UI 진단용 — 값 노출 없이 설정 여부만 반환."""
    values = parse_env_file()
    found_keys = [k for k in values if k.startswith("SUPABASE")]
    return {
        "env_file_exists": ENV_FILE.is_file(),
        "env_file": str(ENV_FILE),
        "url_set": bool(get_supabase_url()),
        "key_set": bool(get_supabase_anon_key()),
        "found_keys": ", ".join(found_keys) if found_keys else "(없음)",
    }


def require_anthropic_api_key() -> str:
    key = get_anthropic_api_key()
    if not key:
        raise ValueError(
            f"ANTHROPIC_API_KEY를 찾을 수 없습니다. "
            f"`{ENV_FILE}` 파일에 `ANTHROPIC_API_KEY=sk-ant-...` 형식으로 저장하세요."
        )
    return key


def api_key_preview(key: str | None) -> str:
    """화면 표시용 — 키 앞 10자만 반환."""
    if not key:
        return "(없음)"
    return key[:10]

"""`.env` 파일을 open()으로 직접 읽어 API 키를 파싱합니다."""

from __future__ import annotations

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
    """os.environ 없이 `.env` 파일 내용만으로 API 키를 반환합니다."""
    values = parse_env_file()
    return normalize_api_key(values.get("ANTHROPIC_API_KEY"))


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

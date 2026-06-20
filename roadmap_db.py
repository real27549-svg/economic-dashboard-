"""Supabase 재테크 로드맵 데이터 저장."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import env_config

_client = None


def _reset_client() -> None:
    global _client
    _client = None


def is_supabase_configured() -> bool:
    return bool(env_config.get_supabase_url() and env_config.get_supabase_anon_key())


def get_client():
    global _client
    url = env_config.get_supabase_url()
    key = env_config.get_supabase_anon_key()
    if not url or not key:
        _client = None
        return None
    if _client is not None:
        return _client
    try:
        from supabase import create_client

        _client = create_client(url, key)
        return _client
    except Exception:
        _client = None
        return None


def ensure_user(local_id: str) -> None:
    client = get_client()
    if not client:
        raise RuntimeError("Supabase가 설정되지 않았습니다.")
    client.table("roadmap_users").upsert({"local_id": local_id}).execute()


def get_fixed_profile(local_id: str) -> dict[str, Any]:
    client = get_client()
    if not client:
        return {}
    resp = (
        client.table("roadmap_fixed_profiles")
        .select("data")
        .eq("local_id", local_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0]["data"] if rows else {}


def save_fixed_profile(local_id: str, data: dict[str, Any]) -> None:
    ensure_user(local_id)
    client = get_client()
    if not client:
        raise RuntimeError("Supabase가 설정되지 않았습니다.")
    payload = {
        "local_id": local_id,
        "data": data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("roadmap_fixed_profiles").upsert(payload).execute()


def get_monthly_snapshot(local_id: str, year_month: str) -> dict[str, Any]:
    client = get_client()
    if not client:
        return {}
    resp = (
        client.table("roadmap_monthly_snapshots")
        .select("data, net_assets_man")
        .eq("local_id", local_id)
        .eq("year_month", year_month)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return {}
    row = rows[0]
    data = row.get("data") or {}
    if row.get("net_assets_man") is not None:
        data["_net_assets_man"] = float(row["net_assets_man"])
    return data


def save_monthly_snapshot(
    local_id: str,
    year_month: str,
    data: dict[str, Any],
    net_assets_man: float,
) -> None:
    ensure_user(local_id)
    client = get_client()
    if not client:
        raise RuntimeError("Supabase가 설정되지 않았습니다.")
    payload = {
        "local_id": local_id,
        "year_month": year_month,
        "data": data,
        "net_assets_man": net_assets_man,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("roadmap_monthly_snapshots").upsert(
        payload,
        on_conflict="local_id,year_month",
    ).execute()


def list_monthly_history(local_id: str) -> list[dict[str, Any]]:
    client = get_client()
    if not client:
        return []
    resp = (
        client.table("roadmap_monthly_snapshots")
        .select("year_month, net_assets_man, data, updated_at")
        .eq("local_id", local_id)
        .order("year_month")
        .execute()
    )
    return resp.data or []


def get_annual_snapshot(local_id: str, year: int) -> dict[str, Any]:
    client = get_client()
    if not client:
        return {}
    resp = (
        client.table("roadmap_annual_snapshots")
        .select("data")
        .eq("local_id", local_id)
        .eq("year", year)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0]["data"] if rows else {}


def save_annual_snapshot(local_id: str, year: int, data: dict[str, Any]) -> None:
    ensure_user(local_id)
    client = get_client()
    if not client:
        raise RuntimeError("Supabase가 설정되지 않았습니다.")
    payload = {
        "local_id": local_id,
        "year": year,
        "data": data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("roadmap_annual_snapshots").upsert(
        payload,
        on_conflict="local_id,year",
    ).execute()


def list_annual_history(local_id: str) -> list[dict[str, Any]]:
    client = get_client()
    if not client:
        return []
    resp = (
        client.table("roadmap_annual_snapshots")
        .select("year, data, updated_at")
        .eq("local_id", local_id)
        .order("year")
        .execute()
    )
    return resp.data or []


def add_variable_event(
    local_id: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    ensure_user(local_id)
    client = get_client()
    if not client:
        raise RuntimeError("Supabase가 설정되지 않았습니다.")
    client.table("roadmap_variable_events").insert(
        {
            "local_id": local_id,
            "event_type": event_type,
            "data": data,
        }
    ).execute()


def list_variable_events(local_id: str) -> list[dict[str, Any]]:
    client = get_client()
    if not client:
        return []
    resp = (
        client.table("roadmap_variable_events")
        .select("id, event_type, data, recorded_at")
        .eq("local_id", local_id)
        .order("recorded_at", desc=True)
        .execute()
    )
    return resp.data or []


def test_supabase_connection() -> dict[str, Any]:
    """Supabase 연결·테이블·읽기/쓰기 테스트."""
    _reset_client()
    url = env_config.get_supabase_url()
    key = env_config.get_supabase_anon_key()
    if not url or not key:
        return {
            "ok": False,
            "step": "config",
            "message": "SUPABASE_URL 또는 SUPABASE_ANON_KEY가 .env에 없습니다.",
        }

    test_id = "__connection_test__"
    tables = (
        "roadmap_users",
        "roadmap_fixed_profiles",
        "roadmap_monthly_snapshots",
        "roadmap_annual_snapshots",
        "roadmap_variable_events",
    )

    try:
        client = get_client()
        if not client:
            return {
                "ok": False,
                "step": "client",
                "message": "Supabase 클라이언트 생성 실패 (supabase 패키지 확인)",
            }

        for table in tables:
            client.table(table).select("*").limit(1).execute()

        ensure_user(test_id)
        save_fixed_profile(test_id, {"test": True, "note": "connection test"})
        profile = get_fixed_profile(test_id)
        if not profile.get("test"):
            return {
                "ok": False,
                "step": "write_read",
                "message": "고정 프로필 저장 후 읽기 검증 실패",
            }

        client.table("roadmap_users").delete().eq("local_id", test_id).execute()

        return {
            "ok": True,
            "message": "Supabase 연결 성공 - 5개 테이블 조회/쓰기/삭제 모두 통과",
            "url_preview": url[:30] + "..." if len(url) > 30 else url,
            "tables": list(tables),
        }
    except Exception as exc:
        return {
            "ok": False,
            "step": "runtime",
            "message": str(exc),
        }

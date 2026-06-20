"""Supabase에 roadmap_stock_holdings 테이블 생성.

사용법:
  1) Supabase Dashboard → Settings → Database → Connection string (URI)
     를 `.env`에 `DATABASE_URL=postgresql://...` 로 저장
  2) pip install psycopg2-binary
  3) python scripts/migrate_stock_holdings.py

또는 Supabase SQL Editor에서 supabase/migration_stock_holdings.sql 실행.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import env_config  # noqa: E402

MIGRATION = ROOT / "supabase" / "migration_stock_holdings.sql"


def _sql_editor_url() -> str | None:
    url = env_config.get_supabase_url() or ""
    # https://xxxx.supabase.co → project ref xxxx
    if ".supabase.co" not in url:
        return None
    ref = url.replace("https://", "").replace("http://", "").split(".")[0]
    return f"https://supabase.com/dashboard/project/{ref}/sql/new"


def main() -> int:
    db_url = env_config._env_lookup("DATABASE_URL") or env_config._env_lookup(
        "SUPABASE_DB_URL"
    )
    if not db_url:
        print("DATABASE_URL이 .env에 없습니다.")
        print()
        print("Supabase Dashboard → Project Settings → Database → Connection string (URI)")
        print("를 복사해 .env에 추가하세요:")
        print("  DATABASE_URL=postgresql://postgres.[ref]:[PASSWORD]@...")
        editor = _sql_editor_url()
        if editor:
            print()
            print(f"SQL Editor: {editor}")
        print()
        print(f"또는 `{MIGRATION}` 내용을 SQL Editor에 붙여넣어 실행하세요.")
        return 1

    try:
        import psycopg2
    except ImportError:
        print("psycopg2-binary가 필요합니다: pip install psycopg2-binary")
        return 1

    if not MIGRATION.is_file():
        print(f"마이그레이션 파일 없음: {MIGRATION}")
        return 1

    sql = MIGRATION.read_text(encoding="utf-8")
    print("Connecting to database...")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.close()
    except Exception as exc:
        print(f"마이그레이션 실패: {exc}")
        return 1

    print("완료: roadmap_stock_holdings 테이블이 생성되었습니다.")
    print("대시보드를 새로고침하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

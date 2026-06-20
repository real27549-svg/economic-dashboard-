-- 재테크 로드맵 Supabase 스키마
-- Supabase SQL Editor에서 실행하세요.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS roadmap_users (
  local_id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roadmap_fixed_profiles (
  local_id TEXT PRIMARY KEY REFERENCES roadmap_users(local_id) ON DELETE CASCADE,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roadmap_monthly_snapshots (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  local_id TEXT NOT NULL REFERENCES roadmap_users(local_id) ON DELETE CASCADE,
  year_month TEXT NOT NULL,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  net_assets_man NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (local_id, year_month)
);

CREATE INDEX IF NOT EXISTS idx_monthly_local_ym
  ON roadmap_monthly_snapshots (local_id, year_month);

CREATE TABLE IF NOT EXISTS roadmap_annual_snapshots (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  local_id TEXT NOT NULL REFERENCES roadmap_users(local_id) ON DELETE CASCADE,
  year INTEGER NOT NULL,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (local_id, year)
);

CREATE TABLE IF NOT EXISTS roadmap_variable_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  local_id TEXT NOT NULL REFERENCES roadmap_users(local_id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_variable_local_time
  ON roadmap_variable_events (local_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS roadmap_stock_holdings (
  local_id TEXT PRIMARY KEY REFERENCES roadmap_users(local_id) ON DELETE CASCADE,
  data JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- RLS (로그인 없이 anon key + local_id로 사용)
ALTER TABLE roadmap_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE roadmap_fixed_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE roadmap_monthly_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE roadmap_annual_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE roadmap_variable_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE roadmap_stock_holdings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "roadmap_users_anon_all" ON roadmap_users
  FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "roadmap_fixed_anon_all" ON roadmap_fixed_profiles
  FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "roadmap_monthly_anon_all" ON roadmap_monthly_snapshots
  FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "roadmap_annual_anon_all" ON roadmap_annual_snapshots
  FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "roadmap_variable_anon_all" ON roadmap_variable_events
  FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "roadmap_holdings_anon_all" ON roadmap_stock_holdings
  FOR ALL TO anon USING (true) WITH CHECK (true);

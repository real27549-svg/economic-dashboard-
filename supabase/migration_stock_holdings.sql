-- 종목별 보유 주식 테이블 (기존 DB에 추가 실행)
-- Supabase Dashboard → SQL Editor → New query → Run

CREATE TABLE IF NOT EXISTS roadmap_stock_holdings (
  local_id TEXT PRIMARY KEY REFERENCES roadmap_users(local_id) ON DELETE CASCADE,
  data JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE roadmap_stock_holdings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'roadmap_stock_holdings'
      AND policyname = 'roadmap_holdings_anon_all'
  ) THEN
    CREATE POLICY "roadmap_holdings_anon_all" ON roadmap_stock_holdings
      FOR ALL TO anon USING (true) WITH CHECK (true);
  END IF;
END $$;

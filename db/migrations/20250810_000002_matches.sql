-- Follow-up migration: create matches and API log tables

-- TFT matches
CREATE TABLE IF NOT EXISTS porygon.matches_tft (
  id VARCHAR(64) PRIMARY KEY,
  match_data JSONB NOT NULL,
  players TEXT[] NOT NULL,
  api_version VARCHAR(16) NOT NULL
);

-- LoL matches
CREATE TABLE IF NOT EXISTS porygon.matches_lol (
  id VARCHAR(64) PRIMARY KEY,
  match_data JSONB NOT NULL,
  players TEXT[] NOT NULL,
  api_version VARCHAR(16) NOT NULL
);

-- API call logs
CREATE TABLE IF NOT EXISTS porygon.log_api (
  id BIGSERIAL PRIMARY KEY,
  provider VARCHAR(64) NOT NULL,
  endpoint VARCHAR(128) NOT NULL,
  requesting_user VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  args JSONB NOT NULL DEFAULT '{}'::jsonb,
  full_call TEXT NOT NULL
);


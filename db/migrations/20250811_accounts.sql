CREATE TABLE IF NOT EXISTS porygon.accounts (
  discord_id VARCHAR(32) NOT NULL,
  puuid VARCHAR(78) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (discord_id, puuid)
);


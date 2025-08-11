-- Initial merged schema for users and messages
create schema if not exists porygon;

-- Users table
CREATE TABLE IF NOT EXISTS porygon.users (
  id BIGSERIAL PRIMARY KEY,
  discord_id TEXT UNIQUE NOT NULL,
  username TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Messages table
CREATE TABLE IF NOT EXISTS porygon.messages (
  id BIGSERIAL PRIMARY KEY,
  discord_channel_id TEXT NOT NULL,
  discord_message_id TEXT UNIQUE NOT NULL,
  author_id TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_channel_created ON messages (discord_channel_id, created_at DESC);


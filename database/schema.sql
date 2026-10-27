-- PostgreSQL Schema for Omnichannel Messaging v7

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table for conversations
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_key TEXT UNIQUE NOT NULL, -- channel:user_id
    channel TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    current_state TEXT DEFAULT 'new_lead',
    assigned_to TEXT, -- actor_id
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table for messages
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id),
    external_id TEXT UNIQUE, -- Provider ID
    idempotency_key TEXT UNIQUE, -- channel:external_id:type
    channel TEXT NOT NULL,
    direction TEXT NOT NULL, -- inbound, outbound
    actor_type TEXT NOT NULL, -- human, bot, agent
    actor_id TEXT NOT NULL,
    content JSONB NOT NULL,
    status TEXT DEFAULT 'received',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    provider_at TIMESTAMPTZ
);

-- Index for searching history
CREATE INDEX IF NOT EXISTS idx_msg_conv_time ON messages (conversation_id, created_at DESC);

-- Table for Pub/Sub subscriptions (Webhooks)
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    webhook_url TEXT NOT NULL,
    auth_token TEXT,
    events JSONB NOT NULL DEFAULT '["message.normalized", "message.status_updated"]',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_webhook_url UNIQUE (webhook_url)
);

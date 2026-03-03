-- SadCat Leaderboard DB Init

CREATE TABLE IF NOT EXISTS leaderboard (
    id          SERIAL PRIMARY KEY,
    rank        INTEGER NOT NULL,
    username    VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    score       BIGINT NOT NULL DEFAULT 0,
    avatar_b64  TEXT,
    extra_data  JSONB,
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contest_info (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(512) NOT NULL,
    description TEXT,
    start_date  TIMESTAMP WITH TIME ZONE,
    end_date    TIMESTAMP WITH TIME ZONE,
    prize_pool  VARCHAR(255),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS parse_logs (
    id          SERIAL PRIMARY KEY,
    parsed_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status      VARCHAR(50) NOT NULL,
    entries_count INTEGER DEFAULT 0,
    error_msg   TEXT
);

-- Migration: add avatar_b64 if not exists
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='leaderboard' AND column_name='avatar_b64'
    ) THEN
        ALTER TABLE leaderboard ADD COLUMN avatar_b64 TEXT;
    END IF;
END $$;

-- Referral leaderboard
CREATE TABLE IF NOT EXISTS ref_leaderboard (
    id          SERIAL PRIMARY KEY,
    rank        INTEGER NOT NULL,
    username    VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    refs        INTEGER NOT NULL DEFAULT 0,
    avatar_b64  TEXT,
    extra_data  JSONB,
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ref_leaderboard_rank ON ref_leaderboard(rank);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_leaderboard_rank ON leaderboard(rank);
CREATE INDEX IF NOT EXISTS idx_leaderboard_username ON leaderboard(username);
CREATE INDEX IF NOT EXISTS idx_leaderboard_score ON leaderboard(score DESC);

-- Gamble calls (from sadcatgamble channel, messages with Solana CA)
CREATE TABLE IF NOT EXISTS gamble_calls (
    id               SERIAL PRIMARY KEY,
    msg_id           BIGINT NOT NULL UNIQUE,
    msg_date         TIMESTAMP WITH TIME ZONE NOT NULL,
    msg_text         TEXT,
    ca_address       VARCHAR(64) NOT NULL,
    token_name       VARCHAR(255),
    token_symbol     VARCHAR(64),
    price_at_call    DOUBLE PRECISION,
    mcap_at_call     DOUBLE PRECISION,
    current_price    DOUBLE PRECISION,
    current_mcap     DOUBLE PRECISION,
    ath_x            DOUBLE PRECISION DEFAULT 0,
    volume_24h       DOUBLE PRECISION,
    liquidity_usd    DOUBLE PRECISION,
    price_change_24h DOUBLE PRECISION,
    dex_url          TEXT,
    is_live          BOOLEAN DEFAULT FALSE,
    updated_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    pair_address     VARCHAR(128),
    ath_atl_final    BOOLEAN DEFAULT FALSE,
    min_x            DOUBLE PRECISION DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS idx_gamble_calls_date ON gamble_calls(msg_date DESC);
CREATE INDEX IF NOT EXISTS idx_gamble_calls_ca   ON gamble_calls(ca_address);

-- Migrations: add columns if not exist (for existing databases)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='gamble_calls' AND column_name='pair_address') THEN
        ALTER TABLE gamble_calls ADD COLUMN pair_address VARCHAR(128);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='gamble_calls' AND column_name='ath_atl_final') THEN
        ALTER TABLE gamble_calls ADD COLUMN ath_atl_final BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='gamble_calls' AND column_name='min_x') THEN
        ALTER TABLE gamble_calls ADD COLUMN min_x DOUBLE PRECISION DEFAULT 1.0;
    END IF;
END $$;

-- Seed contest placeholder
INSERT INTO contest_info (title, description, prize_pool, is_active)
VALUES (
    'SadCat Gamble Contest',
    'Details coming soon... meow :3',
    'TBA',
    true
) ON CONFLICT DO NOTHING;

-- Run this ONCE in your Supabase project → SQL Editor

CREATE TABLE IF NOT EXISTS reels (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename     TEXT NOT NULL,
    caption      TEXT NOT NULL,
    cloudinary_url        TEXT NOT NULL,
    cloudinary_public_id  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'approved', 'rejected', 'posted')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reels_status_created
    ON reels (status, created_at);

-- Personal app — disable RLS so your service_role key has full access
ALTER TABLE reels DISABLE ROW LEVEL SECURITY;

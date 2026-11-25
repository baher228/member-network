CREATE TABLE IF NOT EXISTS thread_runs (
 id bigserial PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT now(),
 n_threads integer NOT NULL,
 n_revive integer NOT NULL,
 llm_status text NOT NULL CHECK (llm_status IN ('available','unavailable','partial')),
 result jsonb NOT NULL
);
ALTER TABLE thread_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON thread_runs FROM anon, authenticated;
REVOKE ALL ON SEQUENCE thread_runs_id_seq FROM anon, authenticated;
GRANT ALL ON thread_runs TO service_role;
GRANT USAGE, SELECT ON SEQUENCE thread_runs_id_seq TO service_role;

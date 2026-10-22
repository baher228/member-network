CREATE SCHEMA IF NOT EXISTS network;
SET LOCAL search_path=network;
DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
END $$;
CREATE TABLE IF NOT EXISTS members (
 id bigserial PRIMARY KEY, name text NOT NULL CHECK (length(trim(name))>0), handle text, github text, devpost text,
 builds text NOT NULL, wants text NOT NULL, speaker_topics text NOT NULL,
 consent_intros boolean NOT NULL DEFAULT false, consent_speaker boolean NOT NULL DEFAULT false,
 is_seed boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS interactions (
 id bigserial PRIMARY KEY, member_id bigint NOT NULL REFERENCES members(id) ON DELETE CASCADE,
 target_id bigint NOT NULL REFERENCES members(id) ON DELETE CASCADE,
 kind text NOT NULL CHECK(kind IN ('like','pass','accept','decline')), is_seed boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), CHECK(member_id<>target_id)
);
CREATE TABLE IF NOT EXISTS intro_runs (
 id bigserial PRIMARY KEY, trigger text NOT NULL CHECK(trigger IN ('manual','scheduled')),
 started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, n_members int NOT NULL DEFAULT 0,
 n_drafted int NOT NULL DEFAULT 0,n_failed int NOT NULL DEFAULT 0,n_skipped int NOT NULL DEFAULT 0,
 llm_status text NOT NULL DEFAULT 'unavailable', notes text
);
CREATE TABLE IF NOT EXISTS intros (
 id bigserial PRIMARY KEY,run_id bigint NOT NULL REFERENCES intro_runs(id),
 member_id bigint NOT NULL REFERENCES members(id) ON DELETE CASCADE,
 target_id bigint NOT NULL REFERENCES members(id) ON DELETE CASCADE,score double precision NOT NULL,
 reasons jsonb NOT NULL DEFAULT '[]',message text,llm_used boolean NOT NULL DEFAULT false,
 status text NOT NULL CHECK(status IN ('drafted','sent','accepted','declined','failed')),error text,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(member_id<>target_id)
);
CREATE TABLE IF NOT EXISTS evidence_cache (
 source text NOT NULL,key text NOT NULL,payload jsonb NOT NULL,fetched_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(source,key)
);
ALTER TABLE members ENABLE ROW LEVEL SECURITY;
ALTER TABLE interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE intro_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE intros ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_cache ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON members,interactions,intro_runs,intros,evidence_cache FROM anon,authenticated;
GRANT USAGE ON SCHEMA network TO anon,authenticated,service_role;
GRANT INSERT(name,handle,github,devpost,builds,wants,speaker_topics,consent_intros,consent_speaker) ON members TO anon;
GRANT USAGE ON SEQUENCE members_id_seq TO anon;
DROP POLICY IF EXISTS questionnaire_insert ON members;
CREATE POLICY questionnaire_insert ON members FOR INSERT TO anon WITH CHECK (is_seed=false);
GRANT ALL ON members,interactions,intro_runs,intros,evidence_cache TO service_role;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA network TO service_role;
CREATE INDEX IF NOT EXISTS interactions_member_idx ON interactions(member_id);
CREATE INDEX IF NOT EXISTS intros_members_idx ON intros(member_id,target_id);

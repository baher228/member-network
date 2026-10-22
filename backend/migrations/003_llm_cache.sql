SET LOCAL search_path=network;
ALTER TABLE network.intros DROP CONSTRAINT intros_status_check;
ALTER TABLE network.intros ADD CONSTRAINT intros_status_check
 CHECK(status IN ('drafted','sent','accepted','declined','failed','skipped'));
CREATE TABLE network.llm_cache (
 member_id bigint NOT NULL REFERENCES network.members(id) ON DELETE CASCADE,
 target_id bigint NOT NULL REFERENCES network.members(id) ON DELETE CASCADE,
 message text NOT NULL CHECK(length(message)>0), created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(member_id,target_id), CHECK(member_id<>target_id)
);
ALTER TABLE network.llm_cache ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON network.llm_cache FROM anon,authenticated;
GRANT ALL ON network.llm_cache TO service_role;
INSERT INTO network.llm_cache(member_id,target_id,message)
 SELECT DISTINCT ON (member_id,target_id) member_id,target_id,message FROM network.intros
 WHERE message IS NOT NULL AND length(message)>0 AND status IN ('drafted','sent','accepted','declined')
 ORDER BY member_id,target_id,created_at,id
 ON CONFLICT DO NOTHING;

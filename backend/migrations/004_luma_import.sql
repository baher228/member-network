SET LOCAL search_path=network;
ALTER TABLE network.members
 ADD COLUMN source text NOT NULL DEFAULT 'questionnaire' CHECK(source IN ('questionnaire','luma')),
 ADD COLUMN opted_in boolean NOT NULL DEFAULT true,
 ADD COLUMN luma_profile_url text UNIQUE,
 ADD COLUMN email text,
 ADD COLUMN x_url text,
 ADD COLUMN instagram_url text,
 ADD COLUMN linkedin_url text,
 ADD COLUMN website_url text;
CREATE TABLE network.events (
 id bigserial PRIMARY KEY, event_name text NOT NULL, event_url text NOT NULL UNIQUE,
 event_date date NOT NULL
);
CREATE TABLE network.attendance (
 member_id bigint NOT NULL REFERENCES network.members(id) ON DELETE CASCADE,
 event_id bigint NOT NULL REFERENCES network.events(id) ON DELETE CASCADE,
 PRIMARY KEY(member_id,event_id)
);
ALTER TABLE network.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE network.attendance ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON network.events,network.attendance FROM anon,authenticated;
GRANT ALL ON network.events,network.attendance TO service_role;
GRANT USAGE,SELECT ON SEQUENCE network.events_id_seq TO service_role;

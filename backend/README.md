# Member Network backend

Python 3.11+, FastAPI/Pydantic v2, PostgreSQL 16. No frontend files are required.

## Setup

From the repository root (install `uv` first if needed: `python3 -m pip install --user uv`):

```sh
uv python install 3.11
uv venv --python 3.11 backend/.venv
uv pip install --python backend/.venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python backend/.venv/bin/python -r backend/requirements.txt
docker run -d --name mn-postgres -e POSTGRES_PASSWORD=membernetwork -e POSTGRES_DB=member_network -p 5432:5432 postgres:16
cd backend
source .venv/bin/activate
python -m app.migrate
python -m app.seed
./run.sh
```

Start existing database: `docker start mn-postgres`. One backend start command from repo root: `backend/run.sh`.
The script applies pending migrations and serves port 8000. API docs: `/docs`; API prefix: `/api`.
Local database credentials above are development-only defaults. For Supabase set `DATABASE_URL` to an owner connection; plain `postgresql://` and `postgres://` URLs work.

All connections use `search_path=network`, locally and on Supabase. A connection hook also
sets it explicitly because session poolers may ignore startup options. Migrations create this
dedicated schema before their `network.schema_migrations` bookkeeping table. Application
tables, sequences, indexes and policies stay in `network`; nothing is migrated from or
changed in `public`. Existing local demo data in `public` is left untouched. On a fresh
`network` schema, run migrations and seed explicitly before starting the API.

Use the Supavisor **session** pooler on port 5432 when the direct IPv6 host is unreachable:
`postgresql+psycopg://postgres.<project-ref>:<url-encoded-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require`
(some regions use `aws-1`). Store this URL only in the ignored `backend/.env`, along with
`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `SUPABASE_SECRET_KEY`. The latter two are
API keys, not database passwords; the SQL backend uses `DATABASE_URL`. Existing Supabase
roles are reused; only missing roles are created for local PostgreSQL.
For a separate verification server without changing port 8000, run from `backend`:
`.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001`.

`backend/.env` is optional and ignored by git; `.env.example` lists environment names only.
`LLM_PROVIDER=cursor` is the default when `CURSOR_API_KEY` is configured and the provider
is unset; otherwise Gemini is the default. `LLM_MODEL` overrides the selected model.
Cursor defaults to `gemini-3.7-flash-high`; `CURSOR_MODEL` is a fallback alias, with
`cursor-grok-4.5-high-fast` another option. Install with `curl -fsS https://cursor.com/install | bash`.
The headless CLI runs with an argv list, no shell, a fresh empty temporary cwd, the key
in its environment only, and a 60-second timeout. It is told not to use tools or files.
JSON is extracted from the envelope's result and validated, never replaced by canned text.
`LLM_PROVIDER=gemini` uses `GEMINI_API_KEY` and `GEMINI_MODEL`
(default `gemini-3.8-flash`) through Google's OpenAI-compatible endpoint. Optional
`LLM_PROVIDER=grok` uses `XAI_API_KEY` and `GROK_MODEL` (default `grok-3-mini`).
Both intros and thread nudges share one client module. Gemini is prompted for JSON without
requiring `response_format`; both providers' JSON is Pydantic-validated. Health reports
the selected `provider` and `model`; `available` means its key is configured, not that
generation or billing has been verified. A depleted-credit HTTP 402 becomes a sanitized
failed draft, with no key or provider response body exposed.
Without the selected provider's key, intros remain drafted with **null messages**, never
canned prose. Generated messages are marked sent for **simulated delivery only**. No
email/SMS is sent. Startup lists available xAI model IDs only when Grok is selected.

Every provider shares a hard cap of **40 generation attempts per backend process**, including
thread nudges and startup probes. Beyond that, requests explicitly fail with `call budget exhausted`.
There are zero application/SDK retries. Cursor skips the startup probe to save calls, so health
is `not_checked` until a real call succeeds or fails; it reports the selected real model.
`INTRO_LLM_MAX_PER_RUN` defaults to 10: the highest-scoring uncached pairs get generation slots;
remaining pairs have status `skipped`, null text and error `skipped: budget cap`.
Successful text is cached by directed `(member_id,target_id)` in `network.llm_cache`, reused
without an LLM call (`llm_used=false`) even across providers. Cache hits do not consume the
run/process call budgets. Demo reset leaves this cache intact; deleting a member removes its
cache entries. Existing successful intro text is backfilled by migration 003.

`EMBEDDER=tf-idf` forces the fast offline fallback. Default uses CPU `all-MiniLM-L6-v2` and caches embeddings by member/text hash; model-load failures are logged and the API reports `tf-idf` honestly. Initial model loading may download Hugging Face weights. Optional `MAX_CF_WEIGHT` (default .7) and `CF_K0` (default 8) control blending.

### Private Luma imports

`POST /api/import/luma` accepts only the exact CSV headers
`name,luma_profile_url,x_url,instagram_url,linkedin_url,github_url,website_url,event_name,event_url,event_date`.
The equivalent CLI is `python -m app.import_luma path.csv`. Imports are transactional, upsert by
normalized Luma URL (then normalized name), and create `events` plus separate `attendance` rows in
`network`; attendance never becomes an interaction or recommender signal. Imported records have
`source=luma`, `opted_in=false`, and both consents false until claimed through the questionnaire.
No external enrichment is performed for them. Keep real files under ignored `data/private/`; never
commit them. The optional LinkedIn URL/headline field is self-entered only; no LinkedIn scraping exists.

`GITHUB_TOKEN` is optional. `LUMA_EVENT_IDS` is a comma-separated allowlist (default `evt-Yz7RR89Zlv56tya`); an empty value skips Luma. External calls use five-second timeouts and parallel source tasks. Evidence responses carry live/cache timestamps and source errors. Devpost sometimes returns HTML rather than JSON; that is reported as a source failure, never fabricated evidence. HN authors and Devpost team members are candidates backed by topic+London search results, **not independently verified London residency or speaking availability**. Devpost results lacking person identities do not create fictional speakers.

Weekly scheduler: Monday 09:00 Europe/London; next occurrence is in `/api/health`. Runs share the same service as the manual endpoint, guarded by an advisory lock. Run a single uvicorn worker for exactly one scheduler. Intro responses are transactional and repeated identical responses do not duplicate interactions.

## Checks

```sh
cd backend
source .venv/bin/activate
pytest -q
python -m app.eval
curl http://localhost:8000/api/health
curl 'http://localhost:8000/api/members/1/recommendations?k=3'
```

The eval CLI uses the same deterministic synthetic dataset as seeding; `/api/eval` evaluates actual seed rows in the database. Both hold out 20% (rounded down, minimum one) of eligible seed likes per user with at least five, across seeds 0..4, reporting mean ± population std without tuning. A controlled cold-start slice caps evaluated users' training likes at two, keeping the held-out targets fixed. GET caches the last successful evaluation in process memory; POST `/api/eval/run` recomputes. See `docs/API.md` for methodology.

All application tables (and migration bookkeeping) have RLS. `anon` has column-limited INSERT on questionnaire members and sequence usage only; no read or other table access. `authenticated` has no app-table access. `service_role` has explicit grants and bypasses RLS locally; Supabase's existing roles are retained. The HTTP API itself is an unauthenticated hackathon/admin demo and connects as database owner: **RLS does not authenticate HTTP callers. Do not expose this API to the public without API authentication/authorization.** Seed identities are fictional, human-looking names labelled by `is_seed`, with no public account handles. Re-seeding updates matching seed members (including legacy demo handles), preserves IDs, and replaces only `is_seed` interactions. **It clears all intros and intro runs for a clean demo.** Non-seed members and interactions are retained. The seed module documents the fixed-RNG generative like process: affinity, tagged build/want complementarity, popularity and noise, independent of the recommender.

CF and content components are independently min-max scaled across eligible candidates for each user; constant components have no discriminative signal and become zero. CF weight is `.7 * n/(n+8)` by default: 0 with no history, .35 at eight interactions, .525 at 24, approaching .7. Content receives the remainder. No weights are adjusted based on evaluation results. Quoted reason snippets are at most 60 characters, truncated at a word boundary with `…`.

Graph degree/density uses unique undirected positive (like/accept) edges; edges include all recorded interaction kinds. Isolation means no positive edges.

## Reset demo safely

`POST /api/demo/reset` restores the fixed-RNG seed profiles and seed-to-seed interactions,
deletes only seed-to-seed intros, then removes intro runs with no remaining intros. All
non-seed members and relationships involving them, surviving run metadata, thread runs
and evidence remain untouched. Unlike the setup CLI `python -m app.seed`, this endpoint
does **not** clear all intros/runs. It uses one transaction in `network`, waits for active
intro runs, and invalidates eval/embedding caches after commit. Repeated resets preserve
the same seed interaction rows, IDs and timestamps. See `docs/API.md` for count semantics.

Response fields (all integer counts): `seed_members_restored`, `seed_members_created`,
`seed_interactions_restored`, `interactions_deleted`, `interactions_created`,
`intros_deleted`, `intro_runs_deleted`. This is an unauthenticated demo/admin endpoint.

Postgres integration tests are opt-in and only allow a local database ending in `_test`:
`DEMO_RESET_TEST_DATABASE_URL=postgresql+psycopg://postgres:membernetwork@localhost:5432/member_network_demo_reset_test pytest -q`.
Create that separate empty test database first; the tests reset only its `network` tables.

## Thread reviver

GET `/api/threads/sample` returns 152 explicitly fictional messages and `suggested_now`.
POST its `log_text` and `suggested_now` as `now` to `/api/threads/analyze` for reproducible
rules. Without `now`, analysis uses the real current UTC time. Discord thread markers
and WhatsApp exports are supported; WhatsApp splits on >36h silence. Revival uses
deterministic silence/participation/question/offer/closing rules, not LLM judgment.
Configure `THREAD_SILENCE_DAYS` (default 3) to change the strict silence threshold.
Only worthy threads get Gemini (or optional Grok) nudge drafts; without a key the nudge is null, never canned.
Nothing is sent. Analyses persist in RLS-protected `thread_runs`; GET `/api/threads/runs`
lists the latest 20 summaries. See `docs/API.md` for exact schemas, scoring and privacy.

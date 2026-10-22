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
Local database credentials above are development-only defaults. For Supabase set `DATABASE_URL` to an owner/service-role connection; plain `postgresql://` and `postgres://` URLs work.

`backend/.env` is optional and ignored by git; `.env.example` lists environment names only. Configure `XAI_API_KEY` and `GROK_MODEL` to enable Grok. Without a key, intros remain drafted with **null messages**, never canned prose. Generated messages are marked sent for **simulated delivery only**. No email/SMS is sent. Startup lists available xAI model IDs when configured. API call errors produce failed intros with sanitized error types.

`EMBEDDER=tf-idf` forces the fast offline fallback. Default uses CPU `all-MiniLM-L6-v2` and caches embeddings by member/text hash; model-load failures are logged and the API reports `tf-idf` honestly. Initial model loading may download Hugging Face weights. Optional `MAX_CF_WEIGHT` (default .7) and `CF_K0` (default 8) control blending.

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

## Thread reviver

GET `/api/threads/sample` returns 152 explicitly fictional messages and `suggested_now`.
POST its `log_text` and `suggested_now` as `now` to `/api/threads/analyze` for reproducible
rules. Without `now`, analysis uses the real current UTC time. Discord thread markers
and WhatsApp exports are supported; WhatsApp splits on >36h silence. Revival uses
deterministic silence/participation/question/offer/closing rules, not LLM judgment.
Configure `THREAD_SILENCE_DAYS` (default 3) to change the strict silence threshold.
Only worthy threads get Grok nudge drafts; without a key the nudge is null, never canned.
Nothing is sent. Analyses persist in RLS-protected `thread_runs`; GET `/api/threads/runs`
lists the latest 20 summaries. See `docs/API.md` for exact schemas, scoring and privacy.

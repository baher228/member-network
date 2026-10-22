# Member Network

**Know your members — Track 2 of the London Grok Bot "Community Engineering" hackathon (22 Oct 2026).**

Most community leads know a member as a phone number. Member Network turns a short opt-in questionnaire into a member graph, then:

1. **Recommends people** with a hybrid recommender — "people who liked who you liked also connected with X" (collaborative filtering) blended with "X builds what you want help with" (sentence embeddings) — and shows *why* for every suggestion.
2. **Runs a weekly intro bot** (button + scheduler) that picks one intro per member, has Gemini (or optional Grok) write a double-opt-in message *only from the structured reasons*, and logs every outcome (drafted / sent / accepted / declined / failed). Accept/decline feeds back into the model, so it keeps working without the organiser.
3. **Finds speakers** for a topic: consenting members plus public London builders, each with evidence from GitHub, Devpost, Hacker News and Luma, labelled live vs cached.
4. **Revives threads**: paste a chat export, rules spot conversations that died on an unanswered question or open offer, Gemini (or optional Grok) drafts the nudge, and the run log shows what it tried and what failed.
5. **Evaluates itself honestly**: hold-out hit-rate@5 / precision@5 for popularity vs CF vs content vs hybrid, including where the hybrid does not win.

MIT licensed. All seeded members are synthetic and labelled **Demo data** in the UI.

## Screens

| Route | Who | What |
| --- | --- | --- |
| `/join` | member (public) | Opt-in questionnaire: builds, wants, speaker topics, GitHub/Devpost, two consent checkboxes |
| `/for-you` | member | Ranked suggestions with CF/content bars and structured reasons; Like / Pass |
| `/intros` | lead | Run weekly intros, run log, per-intro status, accept/decline |
| `/speakers` | lead | Topic → ranked members + public London builders with evidence links |
| `/threads` | lead | Thread reviver on a pasted export (synthetic sample included) |
| `/members` | lead | Member table, consent, force graph with density and isolated members |
| `/eval` | anyone | Offline evaluation panel |

"Viewing as" in the header is the simple member/lead selector (no real auth — explicit hackathon cut).

## Architecture & data flow

```
Questionnaire ──POST /api/members──▶ members (consent flags, is_seed)
Like / Pass ───POST /api/interactions──▶ interactions (like|pass|accept|decline)
                                   │
                         recommender.py (pure functions, in-memory)
             CF: item-item cosine over member×member positive matrix
             Content: all-MiniLM-L6-v2 (wants ⇄ builds), TF-IDF fallback
             Hybrid: per-user min-max, cf_w = 0.7·n/(n+8), content = 1-cf_w
             Exclusions: self, already seen/introduced, no intro consent
                                   │ structured reasons + evidence
          ┌────────────────────────┼────────────────────────┐
   GET /recommendations    POST /intros/run (+ APScheduler Mon 09:00)   GET /eval
                              Gemini (default) / Grok (optional) → Pydantic-validated
                              message from reasons only → intros table
                              accept/decline → interactions → model changes
Speakers: topic → embeddings over consenting members + GitHub/Devpost/HN/Luma (httpx, 5s timeouts, evidence_cache)
Threads:  export text → parser → deterministic revive rules → LLM nudge → thread_runs
```

| Component | Why it exists |
| --- | --- |
| FastAPI + Pydantic v2 | Typed REST contract (`docs/API.md`) so this project can be combined with the sibling project later |
| Postgres (Supabase-compatible SQL migrations with RLS) | Answers and consent stored once; anon may only insert questionnaire rows |
| Item-item CF (numpy/scikit-learn) | The "people who liked X also liked Y" signal the idea is built on; explainable via co-likers |
| sentence-transformers `all-MiniLM-L6-v2` | Cold start: new members have no likes, but their *wants* can match others' *builds* |
| Gemini / optional Grok via OpenAI-compatible APIs | Writes intros/nudges from structured facts only; never decides who is matched |
| APScheduler | Weekly run happens without the organiser |
| httpx + `evidence_cache` | Live public evidence with caching and per-source failure reporting |
| React + Vite + Tailwind + Geist | Calm dark UI matching the hackathon site |
| react-force-graph-2d | Member graph and isolated-member highlighting |

## Setup & run

Requirements: Python 3.11, Node 20+, Docker.

```sh
# database (local stand-in for Supabase; same SQL migrations)
docker run -d --name mn-postgres -e POSTGRES_PASSWORD=membernetwork -e POSTGRES_DB=member_network -p 5432:5432 postgres:16
# (afterwards: docker start mn-postgres)

# backend
python3 -m pip install --user uv
uv python install 3.11
uv venv --python 3.11 backend/.venv
uv pip install --python backend/.venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python backend/.venv/bin/python -r backend/requirements.txt
cp backend/.env.example backend/.env   # optional; fill in keys
cd backend && .venv/bin/python -m app.migrate && .venv/bin/python -m app.seed && cd ..
backend/run.sh                         # http://localhost:8000  (docs at /docs)

# frontend (second terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api → :8000)
```

Default `DATABASE_URL` is the local container above. For Supabase, set `DATABASE_URL` to the pooled connection string and run `python -m app.migrate`.

### Tests & checks

```sh
cd backend && .venv/bin/pytest -q        # core logic: CF, exclusions, hybrid weights, intros w/o LLM, eval, thread rules
cd backend && .venv/bin/python -m app.eval
cd frontend && npm run build
```

### Environment variables (`backend/.env.example`)

`DATABASE_URL`, `LLM_PROVIDER` (`gemini` default, or `grok`), `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-3.8-flash`), optional `XAI_API_KEY` / `GROK_MODEL`, `GITHUB_TOKEN` (optional, raises GitHub rate limit), `LUMA_EVENT_IDS` (comma-separated Luma event ids used as the host pool), `EMBEDDER` (`tf-idf` forces the offline fallback), `MAX_CF_WEIGHT`, `CF_K0`. Supabase uses `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY` and an owner `DATABASE_URL`; all SQL objects live in the dedicated `network` schema. Store credentials only in the ignored `backend/.env`. `DISCORD_BOT_TOKEN` is not used (Discord bot was cut).

## Live vs seeded vs simulated

| Thing | Status |
| --- | --- |
| Members, likes in the demo | **Seeded, synthetic** (`is_seed=true`, "Demo data"), generated by a documented random process (cluster affinity + wants/builds complementarity + popularity + noise), fixed RNG |
| Questionnaire submissions, likes, passes, accept/decline from the UI | **Live**, stored in Postgres |
| Recommendations, eval | **Live** computation over whatever is in the DB |
| Intro / nudge text | **Live Gemini** by default (`GEMINI_API_KEY`), optional Grok (`LLM_PROVIDER=grok`, `XAI_API_KEY`); missing selected key leaves null text, provider errors produce sanitized failed drafts (no canned prose) |
| Intro delivery ("sent") | **Simulated** — nothing is sent to any chat app |
| Speaker evidence | **Live** public API calls (GitHub, Devpost, HN Algolia, Luma event JSON), cached ~6h; each item labelled live/cached with fetch time; source failures shown |
| Thread reviver sample | **Synthetic** chat log bundled in `backend/app/data/`; you can paste a real export |
| Weekly scheduler | Real APScheduler job (Mon 09:00 Europe/London) in the API process; next run time in the header |

## Evaluation

`python -m app.eval` / Evaluation panel: for each seed member with ≥5 likes, hold out 20% of likes, train on the rest, measure whether held-out people appear in the top 5. Averaged over 5 fixed hold-out seeds, plus a cold-start slice (2 training likes per user). Latest run (mean ± population std over 5 splits, 54 users, k=5):

| model | hit-rate@5 | precision@5 | cold-start hit-rate@5 |
| --- | --- | --- | --- |
| popularity | 0.104 ± 0.034 | 0.021 ± 0.007 | 0.089 ± 0.030 |
| CF (item-item) | 0.089 ± 0.044 | 0.018 ± 0.009 | 0.111 ± 0.012 |
| content (MiniLM) | 0.215 ± 0.034 | 0.043 ± 0.007 | 0.211 ± 0.034 |
| hybrid | **0.267 ± 0.042** | **0.053 ± 0.008** | **0.230 ± 0.032** |

Where it doesn't win: **CF alone is no better than popularity** on this data (≈4 training likes per user is too sparse for item-item CF), and the hybrid's lead over content is about one standard deviation. A single earlier split showed CF/content/hybrid tied at 0.148, which is why we now average five splits. Numbers in the panel are recomputed from the live DB, so they move slightly as you add likes in the demo. The seed world is synthetic, so these numbers are a sanity check of the pipeline, not a claim about real communities.

## Decisions

- Plan was agreed up front; remaining choices defaulted and listed here.
- Local `postgres:16` until Supabase credentials exist; same SQL incl. RLS (roles `anon`/`authenticated`/`service_role` created if missing).
- CF weight grows with the member's own interaction count (`0.7·n/(n+8)`); content gets the rest. Not tuned on eval.
- Gemini/Grok never chooses matches; deterministic rules and models do, the LLM only phrases them. Output is Pydantic-validated.
- Speaker "London builders" come from GitHub `location:London` search, Devpost/HN topic search and Luma hosts of configured events; London residency and availability are **not verified**.
- Luma has no public search API without a key, so event ids are configured (`LUMA_EVENT_IDS`).
- Intros count as "sent" only as a simulation label; no Discord/WhatsApp delivery (Discord bot cut for time).
- Matrix factorisation skipped (item-item CF is enough signal and easier to explain).

## Known limitations

- No authentication: the API is an admin/demo API; RLS protects the DB from anon keys, not HTTP callers. Don't expose publicly as-is.
- Synthetic data only in the demo; evaluation on synthetic data.
- Without the selected provider's API key, intro and nudge text are empty by design. Health availability means a key is set, not that credits are available; HTTP 402 creates a failed draft with a sanitized error.
- Devpost sometimes returns HTML instead of JSON; this shows as a failed source.
- One uvicorn worker required (scheduler runs in-process).
- Cut: Discord bot, Notion export, WhatsApp, LinkedIn.

## Reused open-source components

FastAPI (MIT), Pydantic (MIT), SQLAlchemy (MIT), psycopg (LGPL-3.0), httpx (BSD-3), APScheduler (MIT), scikit-learn (BSD-3), numpy (BSD-3), sentence-transformers (Apache-2.0) with `all-MiniLM-L6-v2` (Apache-2.0), PyTorch (BSD-3), OpenAI Python SDK (Apache-2.0, used against Google/xAI APIs), React (MIT), Vite (MIT), Tailwind CSS (MIT), React Router (MIT), Geist fonts (SIL OFL 1.1), react-force-graph-2d (MIT). All application code in this repo is original work written during the event.

## 2-minute demo script

1. **(15s) Problem.** "Leads know members as phone numbers. Nobody gets introduced." Open `/members`: 80 demo members, the graph, 2 isolated members.
2. **(25s) Opt in.** `/join`: fill name, builds "voice agents", wants "help with payments", tick both consents → Join. You're now "Viewing as" the new member.
3. **(25s) For you.** Cold start: CF weight 0, suggestions come from content ("X builds payments infra; you want help with payments"). Like two people → header shows interactions grow, CF weight rises, reasons now include "You liked A and B; N people who liked them also connected with C".
4. **(25s) Weekly intros.** `/intros` → Run weekly intros now. One intro per consenting member, with reasons; Gemini/optional Grok text (or the explicit LLM-unavailable badge). Accept one → "model updated from N interactions"; failures listed, not hidden.
5. **(20s) Speakers.** `/speakers` → "voice agents": consenting members first, then public London builders, each with GitHub repos/stars, Devpost wins, HN posts, Luma events, labelled live/cached.
6. **(10s) Threads.** `/threads` → Load sample → Analyse: dead threads with an unanswered question, drafted nudge, run log.
7. **(10s) Honesty.** `/eval`: hit-rate@5 for popularity/CF/content/hybrid, including where the hybrid doesn't win.

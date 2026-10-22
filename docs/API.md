# Member Network API contract (v1)

Base: `http://localhost:8000/api`. All JSON. Pydantic v2 models mirror these shapes.

## Types
Member = { id:int, name:str, handle:str|null, github:str|null, devpost:str|null,
  builds:str, wants:str, speaker_topics:str, consent_intros:bool, consent_speaker:bool,
  is_seed:bool, created_at:iso, source:"questionnaire"|"luma", opted_in:bool,
  luma_profile_url:str|null, linkedin_url:str|null }
Reason = { kind:"cf"|"content"|"popularity", text:str, weight:float, evidence:object }
  cf evidence: { liked:[{id,name}], co_likers:int }   content evidence: { your_want:str, their_build:str, similarity:float }
Recommendation = { member:Member, score:float, cf_score:float, content_score:float, reasons:[Reason] }
Intro = { id, run_id, member_id, member_name, target_id, target_name, score:float, reasons:[Reason],
  message:str|null, llm_used:bool, status:"drafted"|"sent"|"accepted"|"declined"|"failed"|"skipped",
  error:str|null, created_at, updated_at }
IntroRun = { id, trigger:"manual"|"scheduled", started_at, finished_at|null, n_members:int,
  n_drafted:int, n_failed:int, n_skipped:int, llm_status:"available"|"unavailable"|"partial", notes:str|null }
Evidence = { source:"github"|"devpost"|"hn"|"luma"|"questionnaire", title:str, url:str|null, detail:str|null,
  live:bool, fetched_at:iso|null }
SpeakerCandidate = { kind:"member"|"external", member_id:int|null, name:str, handle:str|null, score:float,
  match_reasons:[str], evidence:[Evidence] }

## Endpoints
GET  /health -> { db:bool, llm:{provider:"cursor"|"gemini"|"grok", available:bool, model:str|null, reason:str|null,
       state:"not_checked"|"working"|"unavailable",
       last_call:{ok:bool, at:iso, http_status:int|null, error:str|null}|null}, n_members:int, n_interactions:int }
POST /members (questionnaire body: Member minus id/is_seed/created_at) -> Member   (422 on invalid)
POST /demo/reset -> { seed_members_restored:int, seed_members_created:int,
       seed_interactions_restored:int, interactions_deleted:int, interactions_created:int,
       intros_deleted:int, intro_runs_deleted:int }
GET  /members -> [ Member & { likes_given:int, likes_received:int, connections:int, isolated:bool } ]
POST /import/luma (multipart field `file`) -> { rows:int, members_created:int, members_matched:int,
       events_created:int, attendance_created:int }
GET  /members/{id} -> Member
GET  /members/{id}/recommendations?k=10 -> { member_id, model:{ n_interactions:int, member_interactions:int,
       cf_weight:float, content_weight:float, embedder:str }, items:[Recommendation] }
POST /interactions { member_id, target_id, kind:"like"|"pass" } -> { ok:true, n_interactions:int }
POST /intros/run { trigger?:"manual" } -> { run:IntroRun, intros:[Intro] }
GET  /intros/runs -> [IntroRun]
GET  /intros?run_id= -> [Intro]
POST /intros/{id}/respond { response:"accepted"|"declined" } -> { intro:Intro, n_interactions:int }
GET  /speakers?topic=...&include_external=true -> { topic, items:[SpeakerCandidate],
       sources:[{ source, status:"live"|"cached"|"failed"|"skipped", error:str|null }] }
GET  /eval -> { computed_at, holdout_fraction:0.2, k:5, n_test_users:int, n_holdout:int,
       results:[{ model:str, hit_rate:float, precision:float, hit_rate_std?:float|null,
                  precision_std?:float|null, slice?:"all"|"cold-start"|null }], notes:[str] }
POST /eval/run -> same as GET /eval (recompute)
GET  /graph -> { nodes:[{id,name,degree,isolated,is_seed}], edges:[{source,target,kind}], metrics:{density:float, n_isolated:int, avg_degree:float} }

### Demo reset
`POST /demo/reset` is an unauthenticated demo/admin operation; do not expose this API publicly.
In one transaction in `network`, it restores the fixed-RNG (42) generated profiles and
the exact generated interaction set between seed members. Ownership is determined by
**both members' `is_seed` flags**, not an interaction's flag: demo UI likes/passes/accepts
between seed members are removed unless they already match a canonical seed interaction.
Relationships involving either non-seed member are untouched, even if marked `is_seed=true`.
Only seed-to-seed intros are deleted, followed by intro runs with no remaining intros.
Non-seed members, mixed/non-seed interactions and intros, surviving run records,
`thread_runs` and evidence caches are unchanged. Eval and in-memory embedding caches are cleared
after commit; the next eval GET recomputes. Failed transactions leave those caches intact.

`seed_members_restored` counts all 80 canonical profiles, including `seed_members_created`
if any were missing. Profiles match existing seed handles (including legacy handles), with
remaining seed IDs used in ascending order for edited handles; non-seed IDs are never reused.
`seed_interactions_restored` is the final canonical relationship count (512), while
`interactions_created`/`interactions_deleted` report actual inserted/deleted rows. Existing
canonical rows are retained; duplicate/noncanonical seed-to-seed rows are removed.
Repeated resets preserve row IDs and timestamps after the first reset, not just matching
relationship counts. There is no reseeding of sequences or deletion of members.

### LLM availability
Health's `llm.provider` is additive. `available` means the selected provider's key is
configured, not that its credits/model are usable. Cursor is the default when its key is set
and `LLM_PROVIDER` is unset, otherwise Gemini. `LLM_MODEL` overrides the selected model;
Cursor defaults to `gemini-3.7-flash-high`, with `CURSOR_MODEL` as a fallback alias.
`state` is `unavailable` if the key is missing or the last generation failed, `working`
after a successful validated generation, and `not_checked` before any generation.
`last_call` records the most recently completed real generation attempt from intros,
threads or the startup probe, in process-wide memory; it resets to null on restart.
Circuit-breaker skips and missing-key shortcuts do not overwrite it. `http_status` is
200 for successful HTTP responses (including invalid structured output), the provider's
status on HTTP errors, or null for failures with no HTTP response and for Cursor CLI calls.
Errors/reasons are sanitized. Process-budget rejections also record an explicit failure.
One small startup probe runs in the background at most once per process when a key is
configured; it never blocks startup or creates intro/thread rows. Cursor skips the probe.

All providers share 40 generation attempts per process, with no application/SDK retries.
Exhaustion fails explicitly with `call budget exhausted`; thread nudges share the same cap.
Intro runs select at most `INTRO_LLM_MAX_PER_RUN` (default 10) uncached pairs by descending
score, with deterministic member/target ID ties. Other selected pairs produce intro rows
with `status:"skipped"`, `message:null`, `llm_used:false`, `error:"skipped: budget cap"` and
increment `n_skipped`, not `n_failed`. These skipped rows do not exclude future matches.
Cached text is stored permanently by directed pair in `network.llm_cache`, including
backfilled successful intros, and reused with `llm_used:false` without spending call slots.
Demo reset preserves the cache. Cached text is reused across models/providers, never regenerated.

Both intro and thread run `llm_status` use actual counts: no key or no drafted outcomes
means `unavailable`; drafted plus failed is `partial`; drafted without failures is
`available`. Skipped/ineligible members/threads do not count as drafted outcomes.

### Speaker result selection
Speaker results keep the same flat `items` array, with at most 30 candidates sorted by score.
Up to 15 slots are reserved for each kind (consenting members and external public builders);
unused slots are filled by the other kind's next-ranked candidates. External evidence matches
therefore remain visible even when member similarity scores are higher. Disabling external
sources or receiving no external candidates still allows up to 30 consenting members.

### Evaluation methodology and cache
`GET /eval` computes on first request and caches the last successful result in memory until
`POST /eval/run` recomputes or the backend restarts. Member/interaction changes do not invalidate it.
`computed_at` identifies the cached computation. Means and population standard deviations are
computed across five fixed holdout seeds (0..4), not across users. These are not confidence intervals.
The original model names remain for slice `all`; extra rows use names such as `cf · cold-start`.
Both slices use the same evaluated users and held-out targets. The cold-start slice caps each
evaluated user's training likes at two simultaneously (other users/non-like interactions remain).
Discarded training likes are not held-out labels. `n_test_users` and `n_holdout` describe one split;
their counts are constant across splits. No hyperparameters are tuned to these metrics.

## Thread reviver

GET `/threads/sample` → `{ log_text:str, suggested_now:iso }`. Bundled **fictional** chat,
152 messages across eight Discord-style threads. `suggested_now` is `2026-10-20T12:00:00Z`.
Pass this explicitly to analyze for a reproducible demo; omitting `now` uses the **real current UTC time**.

POST `/threads/analyze` body `{ log_text:str, now?:iso|null }` →
```
{ run_id:int, parsed_lines:int, skipped_lines:int,
  threads:[{ thread_id:str, title:str, last_message_at:iso, n_messages:int,
    n_participants:int, days_silent:float, ended_with_question:bool,
    unanswered_by:str|null, worth_reviving:bool, score:float, reasons:[str],
    nudge:str|null, llm_used:bool, status:"drafted"|"skipped"|"failed", error:str|null }],
  log:[{ step:str, ok:bool, detail:str }] }
```

Accepted line formats (naive timestamps interpreted as UTC):
```
2026-10-01 18:04 | #channel-or-thread | Maya R.: message
[01/10/2026, 18:04] Maya R.: message
```
Discord markers group threads; WhatsApp messages are sorted chronologically and split on
strictly more than 36 hours of silence. Bad/blank lines are counted and logged individually;
multiline continuations and system messages without an author are not supported. Empty or
entirely invalid input returns an empty analysis with diagnostics, persisted like other runs.
Input limit: 500,000 characters. Dates/times or formats that cannot be parsed are skipped.

Deterministic selection: silence **>3 days** (`THREAD_SILENCE_DAYS`), at least two distinct
participants **or** a terminal unanswered question/open offer, and no closing such as
"thanks"/"solved" unless there is a new question/offer. Only the final message is treated as
unanswered; `unanswered_by` is its author (including open offers). `ended_with_question`
means the final message contains a question mark. Future last messages have zero silence.
Eligible scores sum silence (up to .4 at 14 days), question/offer (.3), participation (up to
.2 at two people), activity (up to .1 at ten messages); ineligible threads score zero.
Each score/decision has concrete reasons. Results are sorted descending by score.

Only selected threads are sent to the configured LLM (Gemini by default, optional Grok)
for a facts-only, Pydantic-validated nudge draft.
Nudges are **never sent**. Missing key: `nudge:null, llm_used:false, status:"drafted"`.
LLM error/invalid JSON: `status:"failed"` and sanitized error. Unselected: `status:"skipped"`.
`run_id` identifies the persisted result JSON; raw exports are not stored separately.
Avoid submitting private chat logs to an untrusted demo; selected last-message facts may
be sent to Google or xAI when the selected provider's API key is configured.

GET `/threads/runs` → last 20 `[{id:int, created_at:iso, n_threads:int, n_revive:int,
llm_status:"available"|"unavailable"|"partial"}]`, newest first. `partial` means at least
one LLM failure; `unavailable` means no key. The `thread_runs` table has RLS and no anon
or authenticated access; backend owner/service-role access only.

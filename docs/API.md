# Member Network API contract (v1)

Base: `http://localhost:8000/api`. All JSON. Pydantic v2 models mirror these shapes.

## Types
Member = { id:int, name:str, handle:str|null, github:str|null, devpost:str|null,
  builds:str, wants:str, speaker_topics:str, consent_intros:bool, consent_speaker:bool,
  is_seed:bool, created_at:iso }
Reason = { kind:"cf"|"content"|"popularity", text:str, weight:float, evidence:object }
  cf evidence: { liked:[{id,name}], co_likers:int }   content evidence: { your_want:str, their_build:str, similarity:float }
Recommendation = { member:Member, score:float, cf_score:float, content_score:float, reasons:[Reason] }
Intro = { id, run_id, member_id, member_name, target_id, target_name, score:float, reasons:[Reason],
  message:str|null, llm_used:bool, status:"drafted"|"sent"|"accepted"|"declined"|"failed",
  error:str|null, created_at, updated_at }
IntroRun = { id, trigger:"manual"|"scheduled", started_at, finished_at|null, n_members:int,
  n_drafted:int, n_failed:int, n_skipped:int, llm_status:"available"|"unavailable"|"partial", notes:str|null }
Evidence = { source:"github"|"devpost"|"hn"|"luma"|"questionnaire", title:str, url:str|null, detail:str|null,
  live:bool, fetched_at:iso|null }
SpeakerCandidate = { kind:"member"|"external", member_id:int|null, name:str, handle:str|null, score:float,
  match_reasons:[str], evidence:[Evidence] }

## Endpoints
GET  /health -> { db:bool, llm:{provider:"gemini"|"grok", available:bool, model:str|null, reason:str|null}, n_members:int, n_interactions:int }
POST /members (questionnaire body: Member minus id/is_seed/created_at) -> Member   (422 on invalid)
GET  /members -> [ Member & { likes_given:int, likes_received:int, connections:int, isolated:bool } ]
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

### LLM availability
Health's `llm.provider` is additive. `available` means the selected provider's key is
configured, not that its credits/model are usable. Gemini is the default; Grok is optional.

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

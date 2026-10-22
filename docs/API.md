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
GET  /health -> { db:bool, llm:{available:bool, model:str|null, reason:str|null}, n_members:int, n_interactions:int }
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

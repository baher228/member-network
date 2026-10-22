from datetime import datetime
from typing import Literal, Any
from pydantic import BaseModel, Field, ConfigDict


class MemberInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200, pattern=r'\S')
    handle: str | None = None
    github: str | None = None
    devpost: str | None = None
    builds: str = Field(max_length=10000)
    wants: str = Field(max_length=10000)
    speaker_topics: str = Field(max_length=10000)
    consent_intros: bool
    consent_speaker: bool


class Member(MemberInput):
    model_config = ConfigDict(extra='ignore')
    id: int
    is_seed: bool
    created_at: datetime


class MemberStats(Member):
    likes_given: int
    likes_received: int
    connections: int
    isolated: bool


class Reason(BaseModel):
    kind: Literal['cf', 'content', 'popularity']
    text: str
    weight: float
    evidence: dict[str, Any]


class Recommendation(BaseModel):
    member: Member
    score: float
    cf_score: float
    content_score: float
    reasons: list[Reason]


class ModelInfo(BaseModel):
    n_interactions: int
    member_interactions: int
    cf_weight: float
    content_weight: float
    embedder: str


class Recommendations(BaseModel):
    member_id: int
    model: ModelInfo
    items: list[Recommendation]


class InteractionInput(BaseModel):
    member_id: int
    target_id: int
    kind: Literal['like', 'pass']


class InteractionResult(BaseModel):
    ok: Literal[True] = True
    n_interactions: int


class Intro(BaseModel):
    id: int
    run_id: int
    member_id: int
    member_name: str
    target_id: int
    target_name: str
    score: float
    reasons: list[Reason]
    message: str | None
    llm_used: bool
    status: Literal['drafted', 'sent', 'accepted', 'declined', 'failed']
    error: str | None
    created_at: datetime
    updated_at: datetime


class IntroRun(BaseModel):
    id: int
    trigger: Literal['manual', 'scheduled']
    started_at: datetime
    finished_at: datetime | None
    n_members: int
    n_drafted: int
    n_failed: int
    n_skipped: int
    llm_status: Literal['available', 'unavailable', 'partial']
    notes: str | None


class RunInput(BaseModel):
    trigger: Literal['manual'] = 'manual'


class RunResult(BaseModel):
    run: IntroRun
    intros: list[Intro]


class RespondInput(BaseModel):
    response: Literal['accepted', 'declined']


class RespondResult(BaseModel):
    intro: Intro
    n_interactions: int


class Evidence(BaseModel):
    source: Literal['github', 'devpost', 'hn', 'luma', 'questionnaire']
    title: str
    url: str | None = None
    detail: str | None = None
    live: bool
    fetched_at: datetime | None = None


class SpeakerCandidate(BaseModel):
    kind: Literal['member', 'external']
    member_id: int | None = None
    name: str
    handle: str | None = None
    score: float
    match_reasons: list[str]
    evidence: list[Evidence]


class SourceStatus(BaseModel):
    source: str
    status: Literal['live', 'cached', 'failed', 'skipped']
    error: str | None = None


class SpeakersResult(BaseModel):
    topic: str
    items: list[SpeakerCandidate]
    sources: list[SourceStatus]


class EvalMetric(BaseModel):
    model: str
    hit_rate: float
    precision: float
    hit_rate_std: float | None = None
    precision_std: float | None = None
    slice: Literal['all', 'cold-start'] | None = None


class EvalResult(BaseModel):
    computed_at: datetime
    holdout_fraction: float = 0.2
    k: int = 5
    n_test_users: int
    n_holdout: int
    results: list[EvalMetric]
    notes: list[str]


class DemoResetResult(BaseModel):
    seed_members_restored: int
    seed_members_created: int
    seed_interactions_restored: int
    interactions_deleted: int
    interactions_created: int
    intros_deleted: int
    intro_runs_deleted: int


class LLMCallResult(BaseModel):
    ok: bool
    at: datetime
    http_status: int | None
    error: str | None


class LLMHealth(BaseModel):
    provider: Literal['gemini', 'grok']
    available: bool
    model: str | None
    reason: str | None
    state: Literal['not_checked', 'working', 'unavailable'] = 'not_checked'
    last_call: LLMCallResult | None = None


class Health(BaseModel):
    db: bool
    llm: LLMHealth
    n_members: int
    n_interactions: int
    scheduler_next_run: datetime | None


class GraphNode(BaseModel):
    id: int
    name: str
    degree: int
    isolated: bool
    is_seed: bool


class GraphEdge(BaseModel):
    source: int
    target: int
    kind: str


class GraphMetrics(BaseModel):
    density: float
    n_isolated: int
    avg_degree: float


class GraphResult(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    metrics: GraphMetrics


class ThreadSample(BaseModel):
    log_text: str
    suggested_now: datetime


class ThreadAnalyzeInput(BaseModel):
    log_text: str = Field(max_length=500000)
    now: datetime | None = None


class ThreadLogEntry(BaseModel):
    step: str
    ok: bool
    detail: str


class ThreadResult(BaseModel):
    thread_id: str
    title: str
    last_message_at: datetime
    n_messages: int
    n_participants: int
    days_silent: float
    ended_with_question: bool
    unanswered_by: str | None
    worth_reviving: bool
    score: float
    reasons: list[str]
    nudge: str | None
    llm_used: bool
    status: Literal['drafted', 'skipped', 'failed']
    error: str | None


class ThreadAnalysis(BaseModel):
    run_id: int
    parsed_lines: int
    skipped_lines: int
    threads: list[ThreadResult]
    log: list[ThreadLogEntry]


class ThreadRunSummary(BaseModel):
    id: int
    created_at: datetime
    n_threads: int
    n_revive: int
    llm_status: Literal['available', 'unavailable', 'partial']

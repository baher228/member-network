from collections import Counter
import asyncio
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from sqlalchemy.exc import IntegrityError
from app import models as m
from app.db import rows, execute, snapshot
from app.services.recommender import recommend
from app.services.intros import run_intros, list_intros, respond
from app.services.llm import health as llm_health
from app.services.speakers import find_speakers
from app.services.graph import graph
from app.eval import get_evaluation
from app.services.demo import reset_demo
from app.services.member_identity import submit_questionnaire
from app.import_luma import import_csv, MAX_BYTES
from app.cognee_client import health as cognee_health

router = APIRouter(prefix='/api')
scheduler = None


@router.get('/health', response_model=m.Health)
def health():
    db, n_members, n_interactions = True, 0, 0
    try:
        counts = rows('SELECT (SELECT count(*) FROM members) AS members,(SELECT count(*) FROM interactions) AS interactions')[0]
        n_members, n_interactions = counts['members'], counts['interactions']
    except Exception:
        db = False
    job = scheduler.get_job('weekly-intros') if scheduler else None
    return dict(db=db, llm=llm_health(), cognee=cognee_health(), n_members=n_members, n_interactions=n_interactions, scheduler_next_run=job.next_run_time if job else None)


@router.post('/demo/reset', response_model=m.DemoResetResult)
def demo_reset():
    return reset_demo()


@router.post('/members', response_model=m.Member)
def create_member(body: m.MemberInput):
    try:
        return submit_questionnaire(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except IntegrityError:
        raise HTTPException(409, 'Member identity conflicts with an existing profile')


@router.post('/import/luma', response_model=m.LumaImportResult)
async def luma_import(file: UploadFile = File(...)):
    try:
        content = await file.read(MAX_BYTES + 1)
        return await asyncio.to_thread(import_csv, content)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        await file.close()


@router.get('/members', response_model=list[m.MemberStats])
def members():
    data, interactions = snapshot()
    given, received = Counter(), Counter()
    connections = {member['id']: set() for member in data}
    network = graph(data, interactions)
    isolated = {n['id']: n['isolated'] for n in network['nodes']}
    for row in interactions:
        if row['kind'] == 'like':
            given[row['member_id']] += 1
            received[row['target_id']] += 1
        if row['kind'] == 'accept':
            connections[row['member_id']].add(row['target_id'])
            connections[row['target_id']].add(row['member_id'])
    return [dict(**member, likes_given=given[member['id']], likes_received=received[member['id']], connections=len(connections[member['id']]), isolated=isolated[member['id']]) for member in data]


@router.get('/members/{member_id}', response_model=m.Member)
def get_member(member_id: int):
    data = rows('SELECT * FROM members WHERE id=:id', {'id': member_id})
    if not data:
        raise HTTPException(404, 'Member not found')
    return data[0]


@router.get('/members/{member_id}/recommendations', response_model=m.Recommendations)
def recommendations(member_id: int, k: int = Query(10, ge=1, le=100)):
    data, interactions = snapshot()
    try:
        return recommend(member_id, data, interactions, rows('SELECT member_id,target_id FROM intros'), k=k)
    except KeyError:
        raise HTTPException(404, 'Member not found')


@router.post('/interactions', response_model=m.InteractionResult)
def interaction(body: m.InteractionInput):
    if body.member_id == body.target_id:
        raise HTTPException(422, 'Self interactions are not allowed')
    identities = rows('SELECT id,opted_in FROM members WHERE id IN (:a,:b)', {'a': body.member_id, 'b': body.target_id})
    if any(not member['opted_in'] for member in identities):
        raise HTTPException(403, 'Interactions require opted-in members')
    try:
        execute('INSERT INTO interactions(member_id,target_id,kind) VALUES (:member_id,:target_id,:kind)', body.model_dump())
    except IntegrityError:
        raise HTTPException(404, 'Member or target not found')
    return dict(ok=True, n_interactions=rows('SELECT count(*) AS n FROM interactions')[0]['n'])


@router.post('/intros/run', response_model=m.RunResult)
def intro_run(body: m.RunInput = m.RunInput()):
    try:
        return run_intros(body.trigger, member_id=body.member_id)
    except KeyError:
        raise HTTPException(404, 'Member not found')
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@router.get('/intros/runs', response_model=list[m.IntroRun])
def intro_runs():
    return rows('SELECT * FROM intro_runs ORDER BY id DESC')


@router.get('/intros', response_model=list[m.Intro])
def intros(run_id: int | None = None):
    return list_intros(run_id)


@router.post('/intros/{intro_id}/respond', response_model=m.RespondResult)
def intro_respond(intro_id: int, body: m.RespondInput):
    try:
        return respond(intro_id, body.response)
    except KeyError:
        raise HTTPException(404, 'Intro not found')
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get('/speakers', response_model=m.SpeakersResult)
async def speakers(topic: str = Query(min_length=1, max_length=200), include_external: bool = True):
    data = await asyncio.to_thread(rows, 'SELECT * FROM members')
    return await find_speakers(topic, data, include_external)


@router.get('/eval', response_model=m.EvalResult)
def evaluation():
    return get_evaluation()


@router.post('/eval/run', response_model=m.EvalResult)
def evaluation_run():
    return get_evaluation(refresh=True)


@router.get('/graph', response_model=m.GraphResult)
def network_graph():
    attendance = rows('''SELECT a.member_id,e.event_name,e.event_url,e.event_date
        FROM attendance a JOIN events e ON e.id=a.event_id ORDER BY e.event_date,e.id''')
    return graph(*snapshot(), attendance=attendance)

from fastapi import APIRouter
from app import models as m
from app.services import threads

router = APIRouter(prefix='/api/threads', tags=['threads'])


@router.get('/sample', response_model=m.ThreadSample)
def sample():
    return threads.sample_chat()


@router.post('/analyze', response_model=m.ThreadAnalysis)
def analyze(body: m.ThreadAnalyzeInput):
    result = threads.analyze_chat(body.log_text, now=body.now)
    return threads.persist_analysis(result)


@router.get('/runs', response_model=list[m.ThreadRunSummary])
def runs():
    return threads.list_runs()

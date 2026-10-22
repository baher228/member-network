import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from app.routes import api, threads
from app.services.intros import check_llm, run_intros

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(check_llm)
    scheduler = BackgroundScheduler(timezone='Europe/London')
    scheduler.add_job(run_intros, 'cron', day_of_week='mon', hour=9, minute=0,
                      kwargs={'trigger': 'scheduled'}, id='weekly-intros', max_instances=1,
                      coalesce=True, misfire_grace_time=3600)
    scheduler.start()
    api.scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)
    api.scheduler = None


app = FastAPI(title='Member Network', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])
app.include_router(api.router)
app.include_router(threads.router)

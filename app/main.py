import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request

from app.db import engine
from app.routers import tasks, users

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tasks-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Менеджер задач", version="1.0.0", lifespan=lifespan)
app.include_router(users.router)
app.include_router(tasks.router)


@app.middleware("http")
async def process_time(request: Request, call_next):
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("%s %s status=500 time=%.6fs", request.method, request.url.path,
                         perf_counter() - started)
        raise
    elapsed = perf_counter() - started
    response.headers["X-Process-Time"] = f"{elapsed:.6f}"
    logger.info("%s %s status=%s time=%.6fs", request.method, request.url.path,
                response.status_code, elapsed)
    return response

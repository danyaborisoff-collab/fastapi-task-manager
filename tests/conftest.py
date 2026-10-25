import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

if os.environ.get("ALLOW_TEST_DB_RESET") != "1":
    raise RuntimeError("Тесты очищают БД. Укажите отдельную тестовую DATABASE_URL и ALLOW_TEST_DB_RESET=1")

from app.config import settings

if not (make_url(settings.database_url).database or "").endswith("_test"):
    raise RuntimeError("Имя тестовой базы должно заканчиваться на _test")

from app.main import app
from app.db import engine


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE tasks, users RESTART IDENTITY CASCADE"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as instance:
        yield instance
    await engine.dispose()

import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_session
from app.main import app


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url or not (make_url(url).database or "").endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL должна указывать на отдельную БД с суффиксом _test")
    if os.environ.get("ALLOW_TEST_DB_RESET") != "1":
        raise RuntimeError("Для очистки тестовой БД требуется ALLOW_TEST_DB_RESET=1")
    engine = create_async_engine(url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_engine):
    async with test_engine.begin() as connection:
        await connection.execute(text("TRUNCATE tasks, users RESTART IDENTITY CASCADE"))
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as instance:
            yield instance
    finally:
        app.dependency_overrides.pop(get_session, None)

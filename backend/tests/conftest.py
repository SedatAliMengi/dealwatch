"""Shared test setup.

Tests use SQLite in memory by default (fast, nothing to install).
Set TEST_DATABASE_URL to run the same tests on PostgreSQL (CI does this).
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.main import create_app
from app.sources.fake import FakeSource

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="session")
def engine():
    engine = make_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    yield make_session_factory(engine)
    # Empty every table after each test so tests never affect each other.
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def fake_source():
    return FakeSource()


@pytest.fixture
def settings():
    return Settings(database_url=TEST_DATABASE_URL, price_source="fake", scheduler_enabled=False)


@pytest.fixture
def client(settings, session_factory, fake_source):
    app = create_app(settings=settings, session_factory=session_factory, source=fake_source)
    with TestClient(app) as test_client:
        yield test_client

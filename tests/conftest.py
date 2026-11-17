import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine

from clinicbot.config import RIYADH
from clinicbot.models import Base, make_session_factory
from clinicbot.scheduling import seed

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=RIYADH)  # Sunday 09:00 in Abha
PHONE = "+966551234567"
VALID_ID = "1012345672"


@pytest.fixture
def session_factory(tmp_path):
    # CI also runs the suite against PostgreSQL by setting TEST_DATABASE_URL.
    # Locally a SQLite file (not :memory:) lets several connections and threads share data.
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    if url.startswith("postgresql"):
        engine = create_engine(url)
        Base.metadata.drop_all(engine)
        engine.dispose()
    factory = make_session_factory(url)
    with factory() as session:
        seed(session, NOW)
    yield factory
    factory.kw["bind"].dispose()


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s

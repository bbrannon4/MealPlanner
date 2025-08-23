# File: core/db.py
from contextlib import contextmanager
from sqlmodel import SQLModel, create_engine, Session

_engine_cache = None

def init_engine(db_path: str):
    global _engine_cache
    if _engine_cache is None:
        _engine_cache = create_engine(f"sqlite:///{db_path}", echo=False)
    return _engine_cache


def init_db(engine):
    from . import schema  # ensure models are imported
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session(engine):
    with Session(engine) as session:
        yield session


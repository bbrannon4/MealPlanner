# File: core/db.py
import os
from contextlib import contextmanager
from sqlmodel import SQLModel, create_engine, Session

_engine_cache = None


def _get_database_url() -> str:
    """Return the database URL from Streamlit secrets, env var, or local SQLite fallback."""
    # Streamlit secrets (cloud deployment)
    try:
        import streamlit as st
        url = st.secrets.get("DATABASE_URL")
        if url:
            return url
    except Exception:
        pass

    # Environment variable (local dev with .env or shell export)
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    # Local SQLite fallback for offline dev
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "data" / "mealplanner.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


def init_engine():
    global _engine_cache
    if _engine_cache is None:
        url = _get_database_url()
        kwargs = {"echo": False}
        if url.startswith("postgresql"):
            # Keep connections alive across Streamlit reruns
            kwargs["pool_pre_ping"] = True
        _engine_cache = create_engine(url, **kwargs)
    return _engine_cache


def init_db(engine):
    from . import schema  # ensure models are imported
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session(engine):
    with Session(engine) as session:
        yield session


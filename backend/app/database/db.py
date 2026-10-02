import json
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base, Question


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url)


def init_db(engine: Engine, questions_path: Path) -> sessionmaker[Session]:
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as db:
        seed_questions(db, questions_path)
    return session_factory


def seed_questions(db: Session, path: Path) -> None:
    for item in json.loads(path.read_text(encoding="utf-8")):
        db.merge(Question(**item))
    db.commit()

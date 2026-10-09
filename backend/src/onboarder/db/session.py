from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from onboarder.settings import get_settings


@dataclass(frozen=True)
class SessionResources:
    engine: Engine
    sessions: sessionmaker[Session]


def create_session_resources(database_url: str | None = None) -> SessionResources:
    url = database_url or get_settings().DATABASE_URL
    engine = create_engine(url)
    return SessionResources(engine, sessionmaker(bind=engine, expire_on_commit=False))


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return create_session_resources(database_url).sessions

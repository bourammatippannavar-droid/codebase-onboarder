from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from onboarder.settings import get_settings


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    url = database_url or get_settings().DATABASE_URL
    engine: Engine = create_engine(url)
    return sessionmaker(bind=engine, expire_on_commit=False)

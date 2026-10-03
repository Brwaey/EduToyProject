import json
from datetime import datetime, timezone
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import ROOT, Settings


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings) -> Engine:
    engine = create_engine(
        "sqlite+pysqlite:///" + str(settings.database_path),
        connect_args={"check_same_thread": False, "timeout": 5},
        json_serializer=lambda value: json.dumps(value, ensure_ascii=False),
    )

    @event.listens_for(engine, "connect")
    def configure_connection(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def migrate(engine: Engine, settings: Settings) -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def make_session_factory(engine: Engine):
    return sessionmaker(engine, expire_on_commit=False)


def migration_head() -> str:
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    return ScriptDirectory.from_config(config).get_current_head()

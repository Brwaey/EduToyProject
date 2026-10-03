from alembic import context

from app import models, models_ai, models_growth, models_m2  # noqa: F401
from app.db import Base


def run(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    from app.config import Settings
    from app.db import make_engine

    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings)
    with engine.begin() as connection:
        run(connection)
    engine.dispose()

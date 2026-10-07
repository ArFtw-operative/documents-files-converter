from alembic import context

from folio import models  # noqa: F401 - registers tables
from folio.db import Base, engine

target_metadata = Base.metadata


def run() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run()

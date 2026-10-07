from logging.config import fileConfig
from pathlib import Path
import sys

repository_api = Path(__file__).resolve().parents[1] / "apps" / "api"
if repository_api.is_dir():
    sys.path.insert(0, str(repository_api))

from alembic import context
from sqlalchemy import engine_from_config, pool
from convertvault.config import settings
from convertvault.database import Base
from convertvault import models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
if config.config_file_name: fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction(): context.run_migrations()

run_migrations_offline() if context.is_offline_mode() else run_migrations_online()

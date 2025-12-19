from __future__ import with_statement

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv

# Resolve paths: backend/alembic/env.py
BACKEND_DIR = Path(__file__).resolve().parents[1]   # .../backend
REPO_DIR = BACKEND_DIR.parent                       # .../CertHub

# Load .env files (backend first, then repo root)
load_dotenv(BACKEND_DIR / ".env")   # se existir
load_dotenv(REPO_DIR / ".env")      # raiz (principal)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado. Crie .env na raiz ou exporte a variável.")

from alembic import context
from sqlalchemy import create_engine, pool

# Add application directory to path
sys.path.append(str(BACKEND_DIR))

from app.db.base import Base  # noqa: E402
from app import models  # noqa: F401, E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    assert DATABASE_URL is not None, "DATABASE_URL must be set"
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool, pool_pre_ping=True)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

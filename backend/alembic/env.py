"""Alembic environment. Uses DATABASE_URL_DIRECT (docs/DATABASE.md section 2)."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.config.settings import Settings
from app.db.models import Base
from app.db.session import normalize_url

config = context.config
target_metadata = Base.metadata


def get_url() -> str:
    # `config.attributes["url"]` lets tests point at a throwaway database.
    url = config.attributes.get("url") or Settings().database_url_direct
    if not url:
        raise RuntimeError(
            "No database URL for Alembic. Set DATABASE_URL_DIRECT (direct or session-mode "
            "connection string) in backend/.env or the environment."
        )
    return normalize_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

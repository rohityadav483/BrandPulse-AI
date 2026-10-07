"""Alembic environment. Uses DATABASE_URL_DIRECT (docs/DATABASE.md section 2)."""

from sqlalchemy import create_engine, pool

from alembic import context
from app.config.settings import Settings
from app.db.models import Base
from app.db.session import normalize_url

config = context.config
target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    # llm_calls is maintained by the existing migration history but is
    # intentionally excluded from Base.metadata.
    if type_ == "table" and name == "llm_calls":
        return False

    # The llm_calls index is ignored along with its migration-owned table.
    if type_ == "index" and name == "ix_llm_calls_analysis_created_at":
        return False

    # This FK exists in migration 0008/database but is intentionally not
    # represented in the ORM model because the current metadata contract
    # expects serp_usage to expose only its analysis_id FK.
    return not (
        type_ == "foreign_key_constraint" and name == "fk_serp_usage_investigation"
    )


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
        include_object=include_object,
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
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

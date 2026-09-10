import os

from alembic import context
from sqlalchemy import create_engine

with create_engine(os.environ["MIGRATION_DATABASE_URL"]).connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()

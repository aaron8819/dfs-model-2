"""Bounded setup, import evidence, authentication and draft history."""

from pathlib import Path

from alembic import op

revision = "0001_increment2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    op.get_bind().exec_driver_sql(sql)


def downgrade() -> None:
    raise RuntimeError("Evidence-preserving migration: restore a separate database for rollback")

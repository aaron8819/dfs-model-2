"""Decision workspace evidence, candidates and entered attestation."""

from pathlib import Path

from alembic import op

revision = "0003_increment4"
down_revision = "0002_increment3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(Path(__file__).with_suffix(".sql").read_text())


def downgrade() -> None:
    raise RuntimeError("Evidence-preserving migration; restore a separate database")

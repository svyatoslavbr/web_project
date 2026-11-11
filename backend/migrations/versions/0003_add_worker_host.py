from alembic import op
import sqlalchemy as sa

revision = "0003_add_worker_host"
down_revision = "0002_create_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("worker_host", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "worker_host")

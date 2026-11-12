from alembic import op
import sqlalchemy as sa

revision = "0004_add_user_is_admin"
down_revision = "0003_add_worker_host"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")

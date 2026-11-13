"""User-owned accounts, sessions, reset tokens, resources and artifacts."""
from alembic import op
import sqlalchemy as sa
revision="0001"
down_revision=None
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("users",sa.Column("id",sa.String(32),primary_key=True),sa.Column("email",sa.String(254),nullable=False,unique=True),sa.Column("password",sa.Text(),nullable=False))
    for name in ["sessions","password_resets"]:
        op.create_table(name,sa.Column("token",sa.String(64),primary_key=True),
                        sa.Column("user_id",sa.String(32),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
                        sa.Column("expires",sa.Float(),nullable=False))
    op.create_index("ix_sessions_user_id","sessions",["user_id"])
    op.create_table("resources",sa.Column("id",sa.String(32),primary_key=True),
                    sa.Column("user_id",sa.String(32),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
                    sa.Column("kind",sa.String(32),nullable=False),sa.Column("name",sa.String(100),nullable=False),
                    sa.Column("payload",sa.Text(),nullable=False),sa.Column("created",sa.Float(),nullable=False))
    op.create_index("ix_resources_user_id","resources",["user_id"])
    op.create_table("artifacts",sa.Column("id",sa.String(32),primary_key=True),
                    sa.Column("user_id",sa.String(32),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
                    sa.Column("data",sa.LargeBinary(),nullable=False))
    op.create_index("ix_artifacts_user_id","artifacts",["user_id"])
def downgrade():
    for table in ["artifacts","resources","password_resets","sessions","users"]:
        op.drop_table(table)

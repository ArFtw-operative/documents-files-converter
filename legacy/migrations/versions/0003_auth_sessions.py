"""Add revocable, rotating authentication sessions."""

from alembic import op
from convertvault.models import AuthSession

revision = "0003_auth_sessions"
down_revision = "0002_library_maturity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    AuthSession.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    AuthSession.__table__.drop(op.get_bind(), checkfirst=True)

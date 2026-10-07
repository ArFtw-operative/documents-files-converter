"""Add persistent PDF Studio projects and revision history."""

from alembic import op

from convertvault.models import PdfEditProject, PdfEditRevision

revision = "0004_pdf_studio"
down_revision = "0003_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    PdfEditProject.__table__.create(bind, checkfirst=True)
    PdfEditRevision.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    PdfEditRevision.__table__.drop(bind, checkfirst=True)
    PdfEditProject.__table__.drop(bind, checkfirst=True)

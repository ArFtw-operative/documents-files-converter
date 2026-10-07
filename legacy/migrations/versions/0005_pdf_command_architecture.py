"""Add enterprise PDF documents, sessions, commands, and recovery snapshots."""

from alembic import op

from convertvault.models import (
    PdfDocument,
    PdfDocumentVersion,
    PdfEditSession,
    PdfEditorCommand,
    PdfRecoverySnapshot,
)

revision = "0005_pdf_command_architecture"
down_revision = "0004_pdf_studio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    PdfDocument.__table__.create(bind, checkfirst=True)
    PdfDocumentVersion.__table__.create(bind, checkfirst=True)
    PdfEditSession.__table__.create(bind, checkfirst=True)
    PdfEditorCommand.__table__.create(bind, checkfirst=True)
    PdfRecoverySnapshot.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    PdfRecoverySnapshot.__table__.drop(bind, checkfirst=True)
    PdfEditorCommand.__table__.drop(bind, checkfirst=True)
    PdfEditSession.__table__.drop(bind, checkfirst=True)
    PdfDocumentVersion.__table__.drop(bind, checkfirst=True)
    PdfDocument.__table__.drop(bind, checkfirst=True)

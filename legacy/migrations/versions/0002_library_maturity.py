"""Add tags, secure shares, application settings, and 64-bit byte counts."""

from alembic import op

from convertvault.models import AppSetting, Share, Tag, file_tags

revision = "0002_library_maturity"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Tag.__table__.create(bind, checkfirst=True)
    file_tags.create(bind, checkfirst=True)
    Share.__table__.create(bind, checkfirst=True)
    AppSetting.__table__.create(bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE users ALTER COLUMN quota_bytes TYPE BIGINT")
        op.execute("ALTER TABLE files ALTER COLUMN size TYPE BIGINT")


def downgrade() -> None:
    bind = op.get_bind()
    AppSetting.__table__.drop(bind, checkfirst=True)
    Share.__table__.drop(bind, checkfirst=True)
    file_tags.drop(bind, checkfirst=True)
    Tag.__table__.drop(bind, checkfirst=True)

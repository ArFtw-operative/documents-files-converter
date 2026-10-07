"""Relational model (architecture §25, §26, Verso Folio decisions D2).

Deviation from §26: scene objects belong to a *page version* instead of a document revision. A
revision maps every page to a (page id, version) pair, so untouched pages share their analysed
scene across revisions, and undo/redo restore the exact earlier scene (and object ids).
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(enum.StrEnum):
    admin = "admin"
    user = "user"


class DocumentStatus(enum.StrEnum):
    processing = "processing"
    ready = "ready"
    failed = "failed"
    deleted = "deleted"


class BatchStatus(enum.StrEnum):
    pending = "pending"
    committed = "committed"
    failed = "failed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), default=Role.user)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    quota_bytes: Mapped[int] = mapped_column(BigInteger)
    mfa_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Blob(Base):
    """Content-addressed file owned by one user. Physical paths never reach the browser (§27)."""

    __tablename__ = "blobs"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(32), default="pdf")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100), default="application/pdf")
    original_blob_key: Mapped[str] = mapped_column(ForeignKey("blobs.key", ondelete="RESTRICT"))
    original_sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    current_revision: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status"),
                                                   default=DocumentStatus.processing, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    info: Mapped[dict] = mapped_column(JSON, default=dict)  # encryption/signature/metadata summary
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_documents_owner_updated", "owner_id", "updated_at"),)


class Page(Base):
    """Stable page identity; survives reorder, rotation and edits."""

    __tablename__ = "pages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PageVersion(Base):
    __tablename__ = "page_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_pt: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_pt: Mapped[float | None] = mapped_column(Float, nullable=True)
    rotation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_box: Mapped[list | None] = mapped_column(JSON, nullable=True)
    page_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|ready|failed
    analyzer_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ocr_status: Mapped[str] = mapped_column(String(32), default="not_needed")
    edited_hints: Mapped[dict] = mapped_column(JSON, default=dict)  # reconciliation hints from the edit
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("page_id", "version", name="uq_page_version"),)


class SceneObjectRow(Base):
    __tablename__ = "scene_objects"
    pk: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True,
                                    autoincrement=True)
    page_version_id: Mapped[str] = mapped_column(ForeignKey("page_versions.id", ondelete="CASCADE"), index=True)
    object_id: Mapped[str] = mapped_column(String(64))
    object_type: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32))
    bbox: Mapped[list] = mapped_column(JSON)
    polygon: Mapped[list | None] = mapped_column(JSON, nullable=True)
    transform: Mapped[list | None] = mapped_column(JSON, nullable=True)
    style: Mapped[dict] = mapped_column(JSON, default=dict)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)  # search (§38)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    z_index: Mapped[int] = mapped_column(Integer, default=0)
    native_ref: Mapped[dict] = mapped_column(JSON, default=dict)
    logical_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    editable: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (Index("ix_scene_objects_version_object", "page_version_id", "object_id"),)


class DocumentRevision(Base):
    __tablename__ = "document_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    parent_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blob_key: Mapped[str] = mapped_column(ForeignKey("blobs.key", ondelete="RESTRICT"))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    page_map: Mapped[list] = mapped_column(JSON)  # [{"page_id": ..., "version": n}, ...]
    kind: Mapped[str] = mapped_column(String(16))  # original|edit|undo|redo|restore
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="valid")
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("document_id", "revision", name="uq_document_revision"),)


class OperationBatch(Base):
    """One logical, undoable user action (§23, §24, §89A.1 "one transaction")."""

    __tablename__ = "operation_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    client_batch_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), default="edit")  # edit|restore
    base_revision: Mapped[int] = mapped_column(Integer)  # what the client saw
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)  # what it was applied to
    result_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    restore_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[BatchStatus] = mapped_column(Enum(BatchStatus, name="batch_status"), default=BatchStatus.pending)
    undone: Mapped[bool] = mapped_column(Boolean, default=False)
    discarded: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    outcome: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("document_id", "client_batch_id", name="uq_batch_idempotency"),
                      Index("ix_batches_document_created", "document_id", "created_at"))


class DocumentOperation(Base):
    __tablename__ = "document_operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("operation_batches.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    page_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    operation_type: Mapped[str] = mapped_column(String(48))
    target_ids: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Export(Base):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(32), default="standard")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    blob_key: Mapped[str | None] = mapped_column(ForeignKey("blobs.key", ondelete="SET NULL"), nullable=True)
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Immutable mutation/auth audit trail (§45). Rows are only ever inserted."""

    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

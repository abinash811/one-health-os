from __future__ import annotations
import uuid
from typing import Optional
from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy import TIMESTAMP

from database import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("pharmacy_id", "name"),
        Index("uq_roles_chain_name", "chain_id", "name", unique=True,
              postgresql_where=text("is_active")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    # Hospital-wide roles (docs/32 P0): owned by the workspace (chain) and usable at every place in it;
    # `pharmacy_id` is only the place it was created at.
    chain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chains.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(
            timezone=True),
        server_default=func.now(),
        nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(
            timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("pharmacy_id", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    # The workspace (hospital) this login belongs to — docs/33_WORKSPACE_SCOPE.md (required since W4).
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chains.id"), nullable=False)
    # The clinic this login is working at right now (EMR screens use it) — docs/32 P2. NULL = none chosen
    # yet; the clinic's own access row is in `user_clinic_access`.
    clinic_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(10))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Separate from the clinical role (Doctor/Receptionist/...): an admin
    # manages users, roles and settings and gets every permission, so one
    # person can be a Doctor AND an admin (Oct 3, 2026).
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    last_login_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(
            timezone=True),
        server_default=func.now(),
        nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(
            timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False)

    role: Mapped[Role] = relationship(back_populates="users")


class UserStoreRole(Base):
    """One row per (person, store) they can access, with their role at
    that specific store — docs/26_MULTI_CHAIN_SCOPE.md's schema sketch.

    Not read by login/permission checks yet — those still use `users.
    pharmacy_id`/`users.role_id` directly, unchanged. This table is kept
    correct going forward (every user-creation path writes a matching row
    here too, not just the old columns) so it's ready for the switcher to
    read from later, without a second backfill pass. For today's
    single-store reality this is exactly one row per user, mirroring their
    `users.pharmacy_id`/`role_id` — multi-store is only ever *adding* a
    second row for a person, never removing this first one."""
    __tablename__ = "user_store_roles"
    __table_args__ = (UniqueConstraint("user_id", "pharmacy_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class UserClinicAccess(Base):
    """One row per (person, clinic) they can open, with their role there — the clinic twin of
    `UserStoreRole` (docs/32_CLINICS_SCOPE.md P2). Roles are workspace-wide."""
    __tablename__ = "user_clinic_access"
    __table_args__ = (UniqueConstraint("user_id", "clinic_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PasswordResetToken(Base):
    """Self-service "Forgot password" flow (docs/15_ROADMAP.md Auth
    Overhaul #6) — a simple reset-token table on top of today's stateless
    JWT, not a full session-management rework (that's #7, separately
    planned). `token_hash` stores a SHA-256 digest, never the raw token —
    the raw value only ever exists in the outgoing email/response, exactly
    like a password is never stored in plaintext. Single-use (`used_at`)
    and 1-hour expiry, both enforced in routers/auth.py.
    """
    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("idx_password_reset_tokens_token_hash", "token_hash", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_logs_pharmacy", "pharmacy_id"),
        Index("idx_audit_logs_entity", "entity_type", "entity_id"),
        Index("idx_audit_logs_user", "user_id"),
        Index("idx_audit_logs_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB)
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(
            timezone=True),
        server_default=func.now(),
        nullable=False)

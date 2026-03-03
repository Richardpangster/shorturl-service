"""SQLAlchemy ORM models for ShortURL Service."""

from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class URL(Base):
    """ORM model for the urls table.

    Stores short code to original URL mappings with expiry and visit tracking.
    """

    __tablename__ = "urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False, index=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    visit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_visited_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)

    __table_args__ = (
        Index("idx_short_code", "short_code"),
        Index("idx_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<URL id={self.id} short_code={self.short_code!r}>"


class User(Base):
    """ORM model for the users table.

    Stores user credentials for authentication.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(default=func.now(), server_default=func.now())

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"

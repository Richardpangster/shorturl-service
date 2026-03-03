"""Authentication router: POST /api/auth/login."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Request body for POST /api/auth/login."""

    username: str = Field(..., min_length=1, max_length=64, description="Username")
    password: str = Field(..., min_length=1, description="Plain-text password")


class LoginResponse(BaseModel):
    """Response body for POST /api/auth/login."""

    token: str = Field(..., description="JWT Bearer access token")
    expires_in: int = Field(..., description="Token lifetime in seconds")


class RegisterRequest(BaseModel):
    """Request body for POST /api/auth/register."""

    username: str = Field(..., min_length=3, max_length=64, description="Desired username")
    password: str = Field(..., min_length=6, description="Plain-text password (min 6 chars)")


class RegisterResponse(BaseModel):
    """Response body for POST /api/auth/register."""

    username: str
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate user and obtain JWT token",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate a user with username/password and return a JWT access token.

    Args:
        body: Login credentials containing username and password.
        db: Async database session (injected by FastAPI).

    Returns:
        A LoginResponse with JWT token and expiry duration.

    Raises:
        HTTPException 401: If credentials are invalid or the user is inactive.
    """
    # Look up the user
    result = await db.execute(select(User).where(User.username == body.username))
    user: Optional[User] = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        logger.warning("Failed login attempt for username=%r", body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    expires_in = settings.access_token_expire_seconds
    token = create_access_token(username=user.username, expires_in=expires_in)

    logger.info("User %r logged in successfully.", user.username)
    return LoginResponse(token=token, expires_in=expires_in)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Register a new user with a hashed password.

    Args:
        body: Registration data containing username and password.
        db: Async database session (injected by FastAPI).

    Returns:
        A RegisterResponse confirming the created username.

    Raises:
        HTTPException 409: If the username is already taken.
    """
    # Check for duplicate username
    result = await db.execute(select(User).where(User.username == body.username))
    existing: Optional[User] = result.scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{body.username}' is already taken",
        )

    hashed = hash_password(body.password)
    new_user = User(username=body.username, hashed_password=hashed)
    db.add(new_user)
    await db.commit()

    logger.info("New user registered: %r", body.username)
    return RegisterResponse(username=body.username, message="User registered successfully")

"""Registration, login and the current account."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.limiter import limiter
from app.models import User
from app.schemas import TokenOut, UserCreate, UserLogin, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter()


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, payload: UserCreate, db: DbSession) -> TokenOut:
    email = payload.email.lower().strip()

    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing is not None:
        # 409 rather than a silent success: the client needs to know to log in.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or email.split("@")[0],
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, payload: UserLogin, db: DbSession) -> TokenOut:
    email = payload.email.lower().strip()
    user = db.scalar(select(User).where(func.lower(User.email) == email))

    if user is None or not verify_password(payload.password, user.password_hash):
        # One message for both cases, so the response cannot be used to
        # discover which emails have accounts.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)

from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from internal.authorization import JWT_ACCESS_SECRET_KEY, JWT_ALGORITHM, verify_password, oauth2_scheme, \
    create_access_token, get_hashed_password, create_refresh_token, JWT_REFRESH_SECRET_KEY
from models.TokenModel import Token, RefreshTokenCreate
from models.UserModel import User, UserCreate


# Create User object and save it to database.
def create_user(session: Session, user_create: UserCreate) -> User:
    hashed_password = get_hashed_password(user_create.password)

    db_user = User(email=user_create.email,
                   fullname=user_create.fullname,
                   password=hashed_password)

    try:
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_user


# Get User object by email.
def get_user_by_email(session: Session, email: str) -> User:
    try:
        statement = select(User).where(User.email == email)
        result = session.exec(statement)
        db_user = result.first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_user


# Get User object by id.
def get_user_by_id(session: Session, id: int) -> User:
    try:
        statement = select(User).where(User.id == id)
        result = session.exec(statement)
        db_user = result.first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_user


# Verify that a user with the specified email and password exists.
def authenticate_user(session: Session, email: str, password: str) -> User:
    user = get_user_by_email(session, email)
    is_password_correct = verify_password(password, user.password)

    if (not user) or (not is_password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_user(session: Session, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Get sub attribute from jwt token which stores the id of the user.
    try:
        payload = jwt.decode(token, JWT_ACCESS_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: int = payload.get("sub")

        if user_id is None:
            raise credentials_exception

    except InvalidTokenError:
        raise credentials_exception

    # Get user with said id.
    db_user = get_user_by_id(session, id=user_id)

    # Check if user with the id mentioned exists in the database.
    if db_user is None:
        raise credentials_exception

    return db_user


# Use email and password to create access and refresh JWT tokens.
def login_for_access_token(session: Session, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    # email is stored as form_data.username to comply with OAuth2 specification of needing username and password fields.
    db_user = authenticate_user(session, form_data.username, form_data.password)

    # Create access and refresh tokens.
    token_data = {"sub": db_user.id}

    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    # Create Token object and save to database.
    db_token = Token(access_token=access_token,
                     refresh_token=refresh_token,
                     token_type="Bearer")

    return db_token


# Verify if refresh token is expired.
def refresh_token_expired(token: Annotated[str, Depends(oauth2_scheme)]):
    try:
        payload = jwt.decode(token, JWT_REFRESH_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        expired_time = datetime.fromtimestamp(payload.get('exp'), timezone.utc)
        current_time = datetime.now(timezone.utc)

        if current_time > expired_time:
            return True
        return False

    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate user.")


def get_access_token_with_refresh_token(session: Session, refresh_token_create: RefreshTokenCreate):
    token = refresh_token_create.refresh_token

    if refresh_token_expired(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is expired.")

    payload = jwt.decode(token, JWT_REFRESH_SECRET_KEY, algorithms=[JWT_ALGORITHM])

    # Create access and refresh tokens with user id as the sub.
    token_data = {"sub": payload.get("sub")}

    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    # Create Token object and save to database.
    db_token = Token(access_token=access_token,
                     refresh_token=refresh_token,
                     token_type="Bearer")

    return db_token

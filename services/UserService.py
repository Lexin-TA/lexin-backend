from typing import Annotated

import jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from jwt import InvalidTokenError, ExpiredSignatureError
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

    # Get user with said id and check if it exists in database.
    db_user = get_user_by_id(session, id=user_id)

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
def check_refresh_token_expiration(token: Annotated[str, Depends(oauth2_scheme)]):
    try:
        jwt.decode(token, JWT_REFRESH_SECRET_KEY, algorithms=[JWT_ALGORITHM])

    except ExpiredSignatureError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def get_access_token_with_refresh_token(session: Session, refresh_token_create: RefreshTokenCreate):
    token = refresh_token_create.refresh_token

    # Check if refresh token expired or not.
    check_refresh_token_expiration(token)

    # Extract payload and see if user exists in database.
    payload = jwt.decode(token, JWT_REFRESH_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    user_id = payload["sub"]

    _ = get_user_by_id(session, user_id)

    # Create access and refresh tokens with user id as the sub.
    token_data = {"sub": user_id}

    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    # Create Token object and save to database.
    db_token = Token(access_token=access_token,
                     refresh_token=refresh_token,
                     token_type="Bearer")

    return db_token

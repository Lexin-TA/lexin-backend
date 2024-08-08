from typing import Annotated

import jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from internal.authorization import JWT_ACCESS_SECRET_KEY, JWT_ALGORITHM, verify_password, oauth2_scheme, \
    create_access_token, get_hashed_password, create_refresh_token
from models.TokenModel import Token
from models.UserModel import User, UserCreate


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


def get_user(session: Session, email: str) -> User:
    try:
        statement = select(User).where(User.email == email)
        result = session.exec(statement)
        db_user = result.first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_user


def authenticate_user(session: Session, email: str, password: str) -> User:
    user = get_user(session, email)
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

    try:
        payload = jwt.decode(token, JWT_ACCESS_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    db_user = get_user(session, email=email)

    if db_user is None:
        raise credentials_exception

    return db_user


def login_for_access_token(session: Session, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> dict:
    db_user = authenticate_user(session, form_data.username, form_data.password)
    access_token = create_access_token(data={"sub": db_user.email})
    refresh_token = create_refresh_token(data={"sub": db_user.email})

    db_token = Token(access_token=access_token, token_type="Bearer")

    try:
        session.add(db_token)
        session.commit()
        session.refresh(db_token)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    result = {
        "access_token": access_token,
        "refresh_token": refresh_token
    }

    return result

import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel
from models import *

# Load Environment Variables.
load_dotenv()

DATABASE_USER = os.getenv('DATABASE_USER')
DATABASE_PASS = os.getenv('DATABASE_PASS')
DATABASE_HOST = os.getenv('DATABASE_HOST')
DATABASE_PORT = os.getenv('DATABASE_PORT')
DATABASE_NAME = os.getenv('DATABASE_NAME')

DATABASE_URL = f"postgresql://{DATABASE_USER}:{DATABASE_PASS}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
DB_ENGINE = create_engine(DATABASE_URL, echo=True, pool_size=16, max_overflow=32)


# Database Session and Table Creation.
def get_session():
    with Session(DB_ENGINE) as session:
        yield session


def create_db_and_tables():
    SQLModel.metadata.create_all(DB_ENGINE, checkfirst=True)


# Common dependencies.
SessionDep = Annotated[Session, Depends(get_session)]

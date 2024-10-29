import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel
from models import *

# Load Environment Variables.
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
DB_ENGINE = create_engine(DATABASE_URL, echo=True)


# Database Session and Table Creation.
def get_session():
    with Session(DB_ENGINE) as session:
        yield session


def create_db_and_tables():
    SQLModel.metadata.create_all(DB_ENGINE, checkfirst=True)


# Common dependencies.
SessionDep = Annotated[Session, Depends(get_session)]

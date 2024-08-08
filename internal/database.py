import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

# Load Environment Variables.
load_dotenv()

DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')

DB_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
DB_ENGINE = create_engine(DB_URL, echo=True)


# Database Session and Table Creation.
def get_session():
    with Session(DB_ENGINE) as session:
        yield session


def create_db_and_tables():
    SQLModel.metadata.create_all(DB_ENGINE)

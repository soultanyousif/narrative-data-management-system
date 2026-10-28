import os

from dotenv import load_dotenv
from sqlalchemy import create_engine


def get_engine():
    load_dotenv()
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    database = os.environ.get("TARGET_DB") or os.environ["POSTGRES_DB"]
    url = f"postgresql+psycopg://{user}:{password}@localhost:5432/{database}"
    return create_engine(url)
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, text

class Settings(BaseSettings):
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432

settings = Settings()  # читает значения из .env через env_file в docker-compose

DATABASE_URL = (
    f"postgresql+psycopg://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def check_db() -> str:
    with engine.connect() as conn:
        ver = conn.execute(text("select version();")).scalar_one()
    return ver

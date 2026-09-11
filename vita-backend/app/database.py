from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {}
if settings.DB_HOST not in ("localhost", "127.0.0.1"):
    connect_args["ssl"] = {"ssl_mode": "REQUIRED"}
    connect_args["connect_timeout"] = 10

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,        # Recycle connections every 5m before cloud NAT/firewall drops them
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

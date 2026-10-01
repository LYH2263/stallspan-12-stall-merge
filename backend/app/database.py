from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_upgrades():
    """Idempotent column additions for databases created before a column existed."""
    with engine.begin() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("vendors")}
        if "status" not in cols:
            conn.execute(text("ALTER TABLE vendors ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'"))

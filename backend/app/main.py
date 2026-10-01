from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def _ensure_vendor_merge_columns():
    """老库补列:vendors.status / vendors.merged_from_json(新库已由 create_all 建好)。"""
    ddl = {
        "status": "ALTER TABLE vendors ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'",
        "merged_from_json": "ALTER TABLE vendors ADD COLUMN merged_from_json TEXT NOT NULL DEFAULT '[]'",
    }
    try:
        with engine.begin() as conn:
            existing = {c["name"] for c in inspect(conn).get_columns("vendors")}
            for col, stmt in ddl.items():
                if col not in existing:
                    conn.execute(text(stmt))
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_vendor_merge_columns()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="StallSpan", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")

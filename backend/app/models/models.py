from datetime import date, datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class MarketDay(Base):
    __tablename__ = "market_days"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    day: Mapped[date] = mapped_column(Date)

class Segment(Base):
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_day_id: Mapped[int] = mapped_column(ForeignKey("market_days.id"))
    name: Mapped[str] = mapped_column(String(64))
    width_m: Mapped[float] = mapped_column(Float)

class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_day_id: Mapped[int] = mapped_column(ForeignKey("market_days.id"))
    name: Mapped[str] = mapped_column(String(64))
    stall_width_m: Mapped[float] = mapped_column(Float)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    # active = 有效可参与分配; merged = 已合并退出; withdrawn = 已撤出
    status: Mapped[str] = mapped_column(String(16), default="active")

class Pillar(Base):
    __tablename__ = "pillars"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    position_m: Mapped[float] = mapped_column(Float)
    thickness_m: Mapped[float] = mapped_column(Float, default=0.4)
    label: Mapped[str] = mapped_column(String(32), default="挡柱")

class AllocationRun(Base):
    __tablename__ = "allocation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    result_json: Mapped[str] = mapped_column(Text, default="{}")

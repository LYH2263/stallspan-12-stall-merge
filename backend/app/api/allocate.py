import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import allocate_first_fit, result_to_dict
router = APIRouter(prefix="/allocate", tags=["allocate"])


def _compute(segment_id: int, db: Session) -> dict:
    """按当前摊主表现算；只纳入仍有效(active)摊主，已合并退出的不再点名。"""
    seg = db.get(Segment, segment_id)
    if not seg: raise HTTPException(404, "街段不存在")
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id,
                                                        Vendor.status == "active")).all()]
    result = result_to_dict(allocate_first_fit(seg.width_m, vendors, pillars))
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    result["pillars"] = pillars
    return result


@router.post("/preview")
def preview(segment_id: int = 1, db: Session = Depends(get_db)):
    """现算：只算不写，零运行行。"""
    return {"id": None, **_compute(segment_id, db)}


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    """确认开间：按刚保存的摊主表现算并落库一条运行行。"""
    result = _compute(segment_id, db)
    run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(result, ensure_ascii=False))
    db.add(run); db.commit(); db.refresh(run)
    return {"id": run.id, **result}


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        return run_allocate(segment_id=segment_id, db=db)
    data = json.loads(run.result_json)
    return {"id": run.id, **data}

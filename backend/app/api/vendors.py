import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Pillar, Segment, Vendor
from app.services.first_fit_engine import free_spans_from_pillars

router = APIRouter(prefix="/vendors", tags=["vendors"])

STATUS_LABELS = {"active": "有效", "merged": "已合并退出", "withdrawn": "已撤出"}


def vendor_dict(v: Vendor) -> dict:
    return {
        "id": v.id,
        "market_day_id": v.market_day_id,
        "name": v.name,
        "stall_width_m": v.stall_width_m,
        "priority": v.priority,
        "status": v.status,
        "status_label": STATUS_LABELS.get(v.status, v.status),
        "merged_from": json.loads(v.merged_from_json or "[]"),
    }


@router.get("")
def list_vendors(db: Session = Depends(get_db)):
    rows = db.scalars(select(Vendor).order_by(Vendor.priority, Vendor.id)).all()
    return [vendor_dict(r) for r in rows]


class MergeRequest(BaseModel):
    vendor_ids: list[int]


def _max_free_span_m(db: Session, market_day_id: int) -> float | None:
    """该集日所有街段里最长的柱间连续空档;没有任何街段时返回 None(不做拟合校验)。"""
    segs = db.scalars(select(Segment).where(Segment.market_day_id == market_day_id)).all()
    if not segs:
        return None
    best = 0.0
    for s in segs:
        pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
                   for p in db.scalars(select(Pillar).where(Pillar.segment_id == s.id)).all()]
        for lo, hi in free_spans_from_pillars(s.width_m, pillars):
            best = max(best, hi - lo)
    return best


@router.post("/merge")
def merge_vendors(req: MergeRequest, db: Session = Depends(get_db)):
    """一次提交把两个仍有效的摊主合成一个占位摊:宽=两者之和,优先级取较高者。

    只改摊主表(原两摊标"已合并退出"),不写任何分配运行行;运行行只在 /allocate/run 确认时落库。
    所有校验先于任何写入,失败整单回滚,不留半成功状态。
    """
    ids = list(dict.fromkeys(req.vendor_ids))
    if len(req.vendor_ids) != 2 or len(ids) != 2:
        raise HTTPException(400, "合并占位需要选定两个不同的摊主")
    a = db.get(Vendor, ids[0])
    b = db.get(Vendor, ids[1])
    if not a or not b:
        raise HTTPException(404, "摊主不存在")
    if a.status != "active" or b.status != "active":
        raise HTTPException(409, "摊主已撤出或已合并退出,不能参与合并")
    if a.market_day_id != b.market_day_id:
        raise HTTPException(400, "两位摊主不属于同一集日,无法合并")

    width = round(a.stall_width_m + b.stall_width_m, 3)
    best = _max_free_span_m(db, a.market_day_id)
    if best is not None and width > best + 1e-9:
        raise HTTPException(
            409,
            f"合并后宽度 {width} m 塞不下任何柱间空档(最大连续空档 {round(best, 3)} m)",
        )

    merged = Vendor(
        market_day_id=a.market_day_id,
        name=f"{a.name}+{b.name}",
        stall_width_m=width,
        priority=min(a.priority, b.priority),
        status="active",
        merged_from_json=json.dumps(
            [
                {"id": a.id, "name": a.name, "stall_width_m": a.stall_width_m, "priority": a.priority},
                {"id": b.id, "name": b.name, "stall_width_m": b.stall_width_m, "priority": b.priority},
            ],
            ensure_ascii=False,
        ),
    )
    a.status = "merged"
    b.status = "merged"
    db.add(merged)
    db.commit()
    db.refresh(merged)
    return {"merged": vendor_dict(merged), "retired_ids": [a.id, b.id]}


@router.post("/{vendor_id}/withdraw")
def withdraw_vendor(vendor_id: int, db: Session = Depends(get_db)):
    """把有效摊主标为已撤出;只改摊主表,不写分配运行行。"""
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "摊主不存在")
    if v.status != "active":
        raise HTTPException(409, "摊主已撤出或已合并退出,不能重复撤出")
    v.status = "withdrawn"
    db.commit()
    db.refresh(v)
    return vendor_dict(v)

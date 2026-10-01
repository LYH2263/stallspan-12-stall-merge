"""合并占位摊验收:一次提交合并、三处一致、失败原子、运行行零写。"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import AllocationRun, MarketDay, Pillar, Segment, Vendor

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)  # 不进 with:不跑 lifespan,不连 Postgres

SEED_VENDORS = [
    ("阿强烧烤", 4.0, 1), ("林记糖水", 3.0, 1), ("老周水果", 5.0, 2),
    ("小美饰品", 2.5, 2), ("大碗面", 6.0, 1), ("手作皮具", 3.5, 3),
    ("巨型舞台车", 12.0, 9),
]


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    day = MarketDay(name="周末夜市", day=date(2026, 9, 20))
    db.add(day); db.flush()
    seg = Segment(market_day_id=day.id, name="东街段", width_m=30.0)
    db.add(seg); db.flush()
    db.add(Pillar(segment_id=seg.id, position_m=10.0, thickness_m=0.5, label="灯柱A"))
    db.add(Pillar(segment_id=seg.id, position_m=20.0, thickness_m=0.5, label="灯柱B"))
    for name, wdt, pri in SEED_VENDORS:
        db.add(Vendor(market_day_id=day.id, name=name, stall_width_m=wdt, priority=pri))
    db.commit()
    db.close()
    yield


def vid(name: str) -> int:
    db = TestingSession()
    try:
        return db.scalar(select(Vendor.id).where(Vendor.name == name))
    finally:
        db.close()


def run_count() -> int:
    db = TestingSession()
    try:
        return db.scalar(select(func.count()).select_from(AllocationRun)) or 0
    finally:
        db.close()


def merge(a: int, b: int):
    return client.post("/api/vendors/merge", json={"vendor_ids": [a, b]})


def test_merge_success_sum_width_and_marks_retired():
    before_runs = run_count()
    r = merge(vid("手作皮具"), vid("小美饰品"))
    assert r.status_code == 200, r.text
    m = r.json()["merged"]
    assert m["stall_width_m"] == 6.0            # 宽 = 两摊之和(3.5 + 2.5)
    assert m["priority"] == 2                   # 优先级取较高者 min(3, 2)
    assert m["status"] == "active"
    assert {x["name"] for x in m["merged_from"]} == {"手作皮具", "小美饰品"}

    rows = client.get("/api/vendors").json()
    by_name = {v["name"]: v for v in rows}
    assert by_name["手作皮具"]["status"] == "merged"
    assert by_name["手作皮具"]["status_label"] == "已合并退出"
    assert by_name["小美饰品"]["status"] == "merged"
    # 列表里有效摊只剩合并摊,宽为两者之和
    active_names = [v["name"] for v in rows if v["status"] == "active"]
    assert "手作皮具" not in active_names and "小美饰品" not in active_names
    assert "手作皮具+小美饰品" in active_names
    assert run_count() == before_runs           # 合并本身零写运行行


def test_merge_then_confirm_uses_merged_not_old_pair():
    merge(vid("手作皮具"), vid("小美饰品"))
    r = client.post("/api/allocate/run?segment_id=1")
    assert r.status_code == 200, r.text
    data = r.json()
    placed = [p["vendor_name"] for p in data["placements"]]
    rejected = [x["vendor_name"] for x in data["rejected"]]
    # 主图与放不下都不得再单独点名原两摊
    assert "手作皮具" not in placed and "手作皮具" not in rejected
    assert "小美饰品" not in placed and "小美饰品" not in rejected
    # 新摊参与随后现算/确认(此处 6m 被挤到放不下)
    assert "手作皮具+小美饰品" in placed + rejected
    # 放不下页(latest)与主图同源一致
    latest = client.get("/api/allocate/latest?segment_id=1").json()
    names = [p["vendor_name"] for p in latest["placements"]] + [x["vendor_name"] for x in latest["rejected"]]
    assert "手作皮具" not in names and "小美饰品" not in names


def test_merge_unfit_fails_atomically():
    before_runs = run_count()
    before_rows = client.get("/api/vendors").json()
    r = merge(vid("大碗面"), vid("老周水果"))   # 6 + 5 = 11 > 最长空档 9.75
    assert r.status_code == 409
    assert "空档" in r.json()["detail"]          # 塞不下文案
    after_rows = client.get("/api/vendors").json()
    assert len(after_rows) == len(before_rows)   # 新摊不出现
    by_name = {v["name"]: v for v in after_rows}
    assert by_name["大碗面"]["status"] == "active"   # 原两摊状态不变
    assert by_name["老周水果"]["status"] == "active"
    assert run_count() == before_runs            # 运行行数不增,不留半成功


def test_merge_inactive_rejected_with_distinct_message():
    assert merge(vid("手作皮具"), vid("小美饰品")).status_code == 200
    r = merge(vid("手作皮具"), vid("阿强烧烤"))  # 已合并摊再合并
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "已合并" in detail or "已撤出" in detail
    assert "空档" not in detail                  # 不得写成空档不够

    client.post(f"/api/vendors/{vid('林记糖水')}/withdraw")
    r2 = merge(vid("林记糖水"), vid("阿强烧烤"))  # 已撤出摊再合并
    assert r2.status_code == 409
    assert "空档" not in r2.json()["detail"]


def test_merge_does_not_touch_third_vendor():
    before = {v["name"]: v["stall_width_m"] for v in client.get("/api/vendors").json()}
    assert merge(vid("手作皮具"), vid("小美饰品")).status_code == 200
    after = {v["name"]: v["stall_width_m"] for v in client.get("/api/vendors").json()}
    for name in ("阿强烧烤", "林记糖水", "老周水果", "大碗面", "巨型舞台车"):
        assert after[name] == before[name]       # 未参与第三摊宽度不变


def test_double_click_merge_keeps_run_rows():
    before_runs = run_count()
    a, b = vid("手作皮具"), vid("小美饰品")
    r1 = merge(a, b)
    r2 = merge(a, b)                              # 连点第二次:已合并,走失败路径
    assert r1.status_code == 200
    assert r2.status_code == 409
    assert run_count() == before_runs            # 运行条数相对合并前不动


def test_latest_filters_merged_without_new_run():
    r = client.post("/api/allocate/run?segment_id=1")
    assert any(p["vendor_name"] == "手作皮具" for p in r.json()["placements"])
    runs_after_confirm = run_count()
    assert merge(vid("手作皮具"), vid("小美饰品")).status_code == 200
    latest = client.get("/api/allocate/latest?segment_id=1").json()
    names = [p["vendor_name"] for p in latest["placements"]] + [x["vendor_name"] for x in latest["rejected"]]
    assert "手作皮具" not in names and "小美饰品" not in names
    assert run_count() == runs_after_confirm     # 合并与查询都不新增运行行


def test_merge_rejects_same_and_missing_vendor():
    a = vid("阿强烧烤")
    assert merge(a, a).status_code == 400
    assert merge(a, 99999).status_code == 404
    assert run_count() == 0


def test_unmerged_baseline_matches_previous_behavior():
    rows = client.get("/api/vendors").json()
    assert len(rows) == 7 and all(v["status"] == "active" for v in rows)
    r = client.post("/api/allocate/run?segment_id=1")
    placed = [p["vendor_name"] for p in r.json()["placements"]]
    rejected = [x["vendor_name"] for x in r.json()["rejected"]]
    assert placed == ["阿强烧烤", "林记糖水", "大碗面", "老周水果", "小美饰品", "手作皮具"]
    assert rejected == ["巨型舞台车"]

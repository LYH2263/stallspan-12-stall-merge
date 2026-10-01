"""合并占位验收：一次提交、三处一致、失败整单回滚、零写运行行、确认才落库。"""
import os

os.environ["DATABASE_URL"] = "sqlite://"  # 应用引擎不落地；测试用下方内存库覆盖 get_db

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import AllocationRun
from app.services.seed import seed_if_empty

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    try:
        seed_if_empty(db)
    finally:
        db.close()


def run_count() -> int:
    db = TestingSession()
    try:
        return db.scalar(select(func.count()).select_from(AllocationRun)) or 0
    finally:
        db.close()


def vendors() -> list[dict]:
    return client.get("/api/vendors").json()


def by_name() -> dict:
    return {v["name"]: v for v in vendors()}


def active_names() -> set:
    return {v["name"] for v in vendors() if v["status"] == "active"}


def merge(a: str, b: str):
    rows = by_name()
    return client.post("/api/vendors/merge",
                       json={"vendor_id_a": rows[a]["id"], "vendor_id_b": rows[b]["id"]})


def test_baseline_unmerged_matches_green():
    rows = vendors()
    assert all(v["status"] == "active" for v in rows)
    assert len(rows) == 7
    res = client.post("/api/allocate/run?segment_id=1")
    assert res.status_code == 200
    names = {p["vendor_name"] for p in res.json()["placements"]} | \
            {r["vendor_name"] for r in res.json()["rejected"]}
    assert {"手作皮具", "小美饰品"} <= names
    assert run_count() == 1


def test_merge_success_list_zero_runs_and_third_vendor_untouched():
    before_runs = run_count()
    res = merge("手作皮具", "小美饰品")
    assert res.status_code == 200
    merged = res.json()["merged"]
    assert merged["stall_width_m"] == 6.0  # 2.5 + 3.5 两摊宽度之和
    assert merged["priority"] == 2         # 取较高优先级(min(3, 2))
    assert merged["status"] == "active"

    rows = by_name()
    # 原两摊在列表标已合并退出，不再出现在有效队列
    assert rows["手作皮具"]["status"] == "merged"
    assert rows["小美饰品"]["status"] == "merged"
    assert "手作皮具" not in active_names()
    assert "小美饰品" not in active_names()
    # 列表只见合并摊且宽为两者之和
    assert merged["name"] in active_names()
    assert by_name()[merged["name"]]["stall_width_m"] == 6.0
    # 合并本身零写运行行
    assert run_count() == before_runs == 0
    # 未参与的第三摊宽度不变
    assert by_name()["阿强烧烤"]["stall_width_m"] == 4.0


def test_confirm_after_merge_uses_saved_merge_not_old_snapshot():
    merge("手作皮具", "小美饰品")
    res = client.post("/api/allocate/run?segment_id=1")
    assert res.status_code == 200
    placed = {p["vendor_name"] for p in res.json()["placements"]}
    rejected = {r["vendor_name"] for r in res.json()["rejected"]}
    # 主图与放不下不得再单独点名原两摊；新摊参与确认
    assert "手作皮具" not in placed | rejected
    assert "小美饰品" not in placed | rejected
    assert "小美饰品+手作皮具" in placed | rejected
    assert run_count() == 1  # 确认开间才落库
    latest = client.get("/api/allocate/latest?segment_id=1").json()
    latest_names = {p["vendor_name"] for p in latest["placements"]} | \
                   {r["vendor_name"] for r in latest["rejected"]}
    assert "手作皮具" not in latest_names and "小美饰品" not in latest_names


def test_preview_writes_no_run_rows():
    before = run_count()
    res = client.post("/api/allocate/preview?segment_id=1")
    assert res.status_code == 200
    assert res.json()["id"] is None
    names = {p["vendor_name"] for p in res.json()["placements"]} | \
            {r["vendor_name"] for r in res.json()["rejected"]}
    assert "手作皮具" in names  # 未合并时与绿仓一致
    assert run_count() == before


def test_merge_too_wide_fails_atomically():
    before_runs = run_count()
    res = merge("大碗面", "老周水果")  # 6 + 5 = 11 m，任一柱间(最大 9.75)都塞不下
    assert res.status_code == 422
    assert "塞不下" in res.json()["detail"]
    rows = by_name()
    assert rows["大碗面"]["status"] == "active"   # 原两摊状态不变
    assert rows["老周水果"]["status"] == "active"
    assert "大碗面+老周水果" not in by_name()      # 新摊不出现
    assert len(vendors()) == 7
    assert run_count() == before_runs            # 运行行数不增


def test_remerge_merged_vendor_rejected_with_distinct_wording():
    ok = merge("手作皮具", "小美饰品")
    assert ok.status_code == 200
    before_runs = run_count()
    again = merge("手作皮具", "小美饰品")  # 连点第二次：已合并摊再合并
    assert again.status_code == 409
    detail = again.json()["detail"]
    assert "已合并" in detail or "已撤出" in detail
    assert "空档" not in detail and "塞不下" not in detail  # 不得写成空档不够
    assert run_count() == before_runs  # 失败路径运行条数相对合并前不动


def test_merge_same_or_unknown_vendor_rejected():
    rows = by_name()
    vid = rows["阿强烧烤"]["id"]
    assert client.post("/api/vendors/merge", json={"vendor_id_a": vid, "vendor_id_b": vid}).status_code == 400
    assert client.post("/api/vendors/merge", json={"vendor_id_a": vid, "vendor_id_b": 99999}).status_code == 404
    assert run_count() == 0

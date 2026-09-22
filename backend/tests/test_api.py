"""通过 FastAPI TestClient 覆盖完整业务流程。"""

import os
import tempfile

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DB_PATH"] = _tmp_db.name
os.environ.setdefault("STATIC_DIR", "/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

db.init_db()
client = TestClient(app)

SEGMENTS = [
    {"id": "seg1", "start": 0, "end": 10, "text": "第一段", "speaker": "记者"},
    {"id": "seg2", "start": 10, "end": 20, "text": "第二段", "speaker": "受访者"},
]


def make_project_with_annotation():
    pid = client.post("/api/projects", json={"name": "测试"}).json()["id"]
    client.post(f"/api/projects/{pid}/import", json={"segments": SEGMENTS})
    r = client.post(
        f"/api/projects/{pid}/annotations",
        json={"segment_id": "seg1", "start": 1, "end": 5,
              "speaker": "记者", "topic": "开场", "note": "基线备注"},
    )
    assert r.status_code == 201
    aid = r.json()["id"]
    return pid, aid


def test_full_merge_workflow():
    pid, aid = make_project_with_annotation()

    # 导出基线
    base_export = client.get(f"/api/projects/{pid}/export").json()
    assert base_export["format"] == "interview-annotator/v1"

    # 两位编辑按同一导出各建离线项目并修改
    pa = client.post("/api/projects/import_export", json={"name": "编辑A", "data": base_export}).json()
    pb = client.post("/api/projects/import_export", json={"name": "编辑B", "data": base_export}).json()

    # A：修改备注；新增区间 12-14
    r = client.put(
        f"/api/projects/{pa['id']}/annotations/{aid}",
        json={"segment_id": "seg1", "start": 1, "end": 5,
              "speaker": "记者", "topic": "开场", "note": "A的备注"},
    )
    assert r.status_code == 200
    r = client.post(
        f"/api/projects/{pa['id']}/annotations",
        json={"segment_id": "seg2", "start": 12, "end": 14, "topic": "A新增"},
    )
    assert r.status_code == 201

    # B：把同一条标注改成别的备注；新增区间 13-16（与 A 的新增重叠）；删除……这里删除无冲突项
    r = client.put(
        f"/api/projects/{pb['id']}/annotations/{aid}",
        json={"segment_id": "seg1", "start": 1, "end": 5,
              "speaker": "记者", "topic": "开场", "note": "B的备注"},
    )
    assert r.status_code == 200
    r = client.post(
        f"/api/projects/{pb['id']}/annotations",
        json={"segment_id": "seg2", "start": 13, "end": 16, "topic": "B新增"},
    )
    assert r.status_code == 201

    export_a = client.get(f"/api/projects/{pa['id']}/export").json()
    export_b = client.get(f"/api/projects/{pb['id']}/export").json()

    # 发起三方合并
    r = client.post(f"/api/projects/{pid}/merge", json={"a": export_a, "b": export_b})
    assert r.status_code == 201
    session = r.json()
    mid = session["id"]
    assert session["stats"]["unchanged"] == 0
    assert len(session["conflicts"]) == 2  # modify_modify + add_add
    types = {c["type"] for c in session["conflicts"]}
    assert types == {"modify_modify", "add_add"}

    # 未全部裁决时不能落库
    r = client.post(f"/api/merges/{mid}/finalize")
    assert r.status_code == 400

    # 逐条裁决：修改冲突取 A；新增冲突 both
    c_mod = next(c for c in session["conflicts"] if c["type"] == "modify_modify")
    c_add = next(c for c in session["conflicts"] if c["type"] == "add_add")
    r = client.post(f"/api/merges/{mid}/resolve",
                    json={"conflict_id": c_mod["id"], "choice": "a"})
    assert r.status_code == 200
    r = client.post(f"/api/merges/{mid}/resolve",
                    json={"conflict_id": c_add["id"], "choice": "both"})
    assert r.status_code == 200

    r = client.post(f"/api/merges/{mid}/finalize")
    assert r.status_code == 201
    merged_pid = r.json()["project_id"]

    merged = client.get(f"/api/projects/{merged_pid}").json()
    notes = {a["id"]: a["note"] for a in merged["annotations"]}
    assert notes[aid] == "A的备注"
    topics = {a["topic"] for a in merged["annotations"]}
    assert {"A新增", "B新增"} <= topics

    # 裁决结果可继续导出
    exported = client.get(f"/api/projects/{merged_pid}/export").json()
    assert len(exported["annotations"]) == 3


def test_single_side_change_fully_auto_merged():
    pid, aid = make_project_with_annotation()
    base_export = client.get(f"/api/projects/{pid}/export").json()
    pa = client.post("/api/projects/import_export", json={"data": base_export}).json()
    client.put(
        f"/api/projects/{pa['id']}/annotations/{aid}",
        json={"segment_id": "seg1", "start": 1, "end": 5,
              "speaker": "记者", "topic": "开场", "note": "A单边改"},
    )
    export_a = client.get(f"/api/projects/{pa['id']}/export").json()
    session = client.post(
        f"/api/projects/{pid}/merge", json={"a": export_a, "b": base_export}
    ).json()
    assert session["conflicts"] == []
    assert session["stats"]["modified"] == 1
    # 无冲突可直接落库
    merged_pid = client.post(f"/api/merges/{session['id']}/finalize").json()["project_id"]
    merged = client.get(f"/api/projects/{merged_pid}").json()
    assert next(a for a in merged["annotations"] if a["id"] == aid)["note"] == "A单边改"


def test_annotation_validation():
    pid = client.post("/api/projects", json={"name": "校验"}).json()["id"]
    client.post(f"/api/projects/{pid}/import", json={"segments": SEGMENTS})
    r = client.post(
        f"/api/projects/{pid}/annotations",
        json={"start": 9, "end": 3, "topic": "非法区间"},
    )
    assert r.status_code == 422


def test_delete_vs_modify_conflict():
    pid, aid = make_project_with_annotation()
    base_export = client.get(f"/api/projects/{pid}/export").json()
    pa = client.post("/api/projects/import_export", json={"data": base_export}).json()
    pb = client.post("/api/projects/import_export", json={"data": base_export}).json()

    client.delete(f"/api/projects/{pa['id']}/annotations/{aid}")
    client.put(
        f"/api/projects/{pb['id']}/annotations/{aid}",
        json={"segment_id": "seg1", "start": 1, "end": 5,
              "speaker": "记者", "topic": "B改", "note": "基线备注"},
    )
    export_a = client.get(f"/api/projects/{pa['id']}/export").json()
    export_b = client.get(f"/api/projects/{pb['id']}/export").json()
    session = client.post(
        f"/api/projects/{pid}/merge", json={"a": export_a, "b": export_b}
    ).json()
    assert len(session["conflicts"]) == 1
    assert session["conflicts"][0]["type"] == "delete_modify"

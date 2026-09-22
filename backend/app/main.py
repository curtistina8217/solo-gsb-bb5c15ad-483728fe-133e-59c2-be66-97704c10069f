"""访谈音频校注 Web 应用 —— FastAPI 后端。

接口概览：
  GET    /api/health
  GET    /api/projects                         项目列表
  POST   /api/projects                         新建项目
  GET    /api/projects/{pid}                   项目详情（片段 + 标注）
  DELETE /api/projects/{pid}                   删除项目
  POST   /api/projects/{pid}/import            导入带时间戳的转写片段
  POST   /api/projects/import_export           按导出 JSON 建项目（离线编辑入口）
  GET    /api/projects/{pid}/export            导出校注 JSON
  POST   /api/projects/demo                    创建示例项目
  POST   /api/projects/{pid}/audio             上传访谈音频
  GET    /api/projects/{pid}/audio             播放音频
  POST   /api/projects/{pid}/annotations       新增区间标注
  PUT    /api/projects/{pid}/annotations/{aid} 修改标注
  DELETE /api/projects/{pid}/annotations/{aid} 删除标注
  POST   /api/projects/{pid}/merge             发起三方合并（A / B 两个离线导出）
  GET    /api/merges/{mid}                     查看合并会话（自动结果 + 冲突）
  POST   /api/merges/{mid}/resolve             提交单条冲突裁决
  POST   /api/merges/{mid}/finalize            全部裁决后生成合并项目
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .merge import FIELDS, apply_resolutions, three_way_merge
from .seed import SAMPLE_ANNOTATIONS, SAMPLE_SEGMENTS

EXPORT_FORMAT = "interview-annotator/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="访谈音频校注", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------- 数据模型 -----------------------------

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SegmentIn(BaseModel):
    id: str | None = None
    start: float
    end: float
    text: str = ""
    speaker: str = ""


class ImportTranscript(BaseModel):
    segments: list[SegmentIn]


class AnnotationIn(BaseModel):
    segment_id: str | None = None
    start: float
    end: float
    speaker: str = ""
    topic: str = ""
    note: str = ""


class ImportExportBody(BaseModel):
    name: str | None = None
    data: dict


class MergeBody(BaseModel):
    a: dict
    b: dict
    name: str | None = None


class ResolveBody(BaseModel):
    conflict_id: str
    choice: str  # a | b | both | custom
    custom: dict | None = None


# ----------------------------- 辅助函数 -----------------------------

def require_project(pid: str) -> dict:
    p = db.get_project_meta(pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


def validate_range(start: float, end: float) -> None:
    if end < start:
        raise HTTPException(422, f"区间结束 {end} 不能早于开始 {start}")
    if start < 0 or end < 0:
        raise HTTPException(422, "时间不能为负数")


def pick_segment(segments: list[dict], start: float, end: float) -> str | None:
    """按重叠时长选择区间主要落在的片段。"""
    best_id, best_overlap = None, 0.0
    for s in segments:
        overlap = max(0.0, min(end, s["end"]) - max(start, s["start"]))
        if overlap > best_overlap:
            best_id, best_overlap = s["id"], overlap
    return best_id


def export_payload(pid: str) -> dict:
    project = db.get_full_project(pid)
    if not project:
        raise HTTPException(404, "项目不存在")
    return {
        "format": EXPORT_FORMAT,
        "project_id": project["id"],
        "name": project["name"],
        "exported_at": db.now(),
        "segments": project["segments"],
        "annotations": project["annotations"],
    }


def parse_export(doc: dict, role: str) -> tuple[list[dict], list[dict]]:
    if not isinstance(doc, dict) or "segments" not in doc:
        raise HTTPException(422, f"{role} 不是有效的校注导出文件（缺少 segments 字段）")
    segments = doc.get("segments") or []
    annotations = doc.get("annotations") or []
    if not isinstance(segments, list) or not isinstance(annotations, list):
        raise HTTPException(422, f"{role} 导出文件格式错误：segments/annotations 必须是数组")
    return segments, annotations


# ----------------------------- 项目 -----------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/projects")
def api_list_projects():
    return db.list_projects()


@app.post("/api/projects", status_code=201)
def api_create_project(body: ProjectCreate):
    return db.create_project(body.name.strip())


@app.get("/api/projects/{pid}")
def api_get_project(pid: str):
    project = db.get_full_project(pid)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@app.delete("/api/projects/{pid}")
def api_delete_project(pid: str):
    require_project(pid)
    db.delete_project(pid)
    return {"ok": True}


@app.post("/api/projects/demo", status_code=201)
def api_create_demo():
    project = db.create_project("示例：乡村教育访谈")
    db.replace_segments(project["id"], SAMPLE_SEGMENTS)
    with db.get_conn() as conn:
        segments = db.get_segments(conn, project["id"])
    for ann in SAMPLE_ANNOTATIONS:
        ann = dict(ann)
        ann["segment_id"] = pick_segment(segments, ann["start"], ann["end"])
        db.create_annotation(project["id"], ann)
    return db.get_full_project(project["id"])


@app.post("/api/projects/{pid}/import")
def api_import_transcript(pid: str, body: dict | list):
    """导入带时间戳的转写片段。接受 {"segments":[...]} 或裸数组。重新导入会清空已有标注。"""
    require_project(pid)
    raw = body.get("segments", []) if isinstance(body, dict) else body
    if not isinstance(raw, list) or not raw:
        raise HTTPException(422, "segments 必须是非空数组")
    segments = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict) or "start" not in s or "end" not in s:
            raise HTTPException(422, f"第 {i + 1} 条片段缺少 start/end")
        start, end = float(s["start"]), float(s["end"])
        validate_range(start, end)
        segments.append(
            {"id": s.get("id"), "start": start, "end": end,
             "text": str(s.get("text", "")), "speaker": str(s.get("speaker", ""))}
        )
    db.replace_segments(pid, segments)
    return db.get_full_project(pid)


@app.post("/api/projects/import_export", status_code=201)
def api_import_export(body: ImportExportBody):
    """依据另一位编辑导出的校注 JSON 建项目（id 保持不变，供后续三方合并）。"""
    segments, annotations = parse_export(body.data, "导入文件")
    name = (body.name or body.data.get("name") or "离线编辑副本").strip()
    project = db.create_project(name)
    db.replace_segments(project["id"], [
        {"id": s.get("id"), "start": float(s.get("start") or 0), "end": float(s.get("end") or 0),
         "text": str(s.get("text", "")), "speaker": str(s.get("speaker", ""))}
        for s in segments
    ])
    valid_seg_ids = {s["id"] for s in segments}
    cleaned = []
    for a in annotations:
        if not a.get("id"):
            continue
        cleaned.append({
            "id": a["id"],
            "segment_id": a.get("segment_id") if a.get("segment_id") in valid_seg_ids else None,
            "start": float(a.get("start") or 0),
            "end": float(a.get("end") or 0),
            "speaker": str(a.get("speaker", "")),
            "topic": str(a.get("topic", "")),
            "note": str(a.get("note", "")),
        })
    db.replace_annotations(project["id"], cleaned)
    return db.get_full_project(project["id"])


@app.get("/api/projects/{pid}/export")
def api_export_project(pid: str):
    require_project(pid)
    payload = export_payload(pid)
    safe_name = payload["name"].encode("ascii", "ignore").decode().strip().replace(" ", "_") or "export"
    return JSONResponse(
        payload,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.json"'},
    )


# ----------------------------- 音频 -----------------------------

@app.post("/api/projects/{pid}/audio", status_code=201)
async def api_upload_audio(pid: str, file: UploadFile = File(...)):
    require_project(pid)
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(422, "仅支持上传音频文件")
    ext = os.path.splitext(file.filename or "")[1] or ".mp3"
    upload_dir = os.path.join(os.path.dirname(db.db_path()), "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, f"{pid}{ext}")
    with open(path, "wb") as f:
        f.write(await file.read())
    db.set_audio_path(pid, path)
    return {"ok": True}


@app.get("/api/projects/{pid}/audio")
def api_get_audio(pid: str):
    project = require_project(pid)
    path = project.get("audio_path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "该项目尚未上传音频")
    return FileResponse(path)


# ----------------------------- 标注 -----------------------------

@app.post("/api/projects/{pid}/annotations", status_code=201)
def api_create_annotation(pid: str, body: AnnotationIn):
    require_project(pid)
    validate_range(body.start, body.end)
    with db.get_conn() as conn:
        segments = db.get_segments(conn, pid)
    segment_id = body.segment_id or pick_segment(segments, body.start, body.end)
    return db.create_annotation(pid, {**body.model_dump(), "segment_id": segment_id})


@app.put("/api/projects/{pid}/annotations/{aid}")
def api_update_annotation(pid: str, aid: str, body: AnnotationIn):
    require_project(pid)
    validate_range(body.start, body.end)
    with db.get_conn() as conn:
        segments = db.get_segments(conn, pid)
    segment_id = body.segment_id or pick_segment(segments, body.start, body.end)
    updated = db.update_annotation(pid, aid, {**body.model_dump(), "segment_id": segment_id})
    if not updated:
        raise HTTPException(404, "标注不存在")
    return updated


@app.delete("/api/projects/{pid}/annotations/{aid}")
def api_delete_annotation(pid: str, aid: str):
    require_project(pid)
    if not db.delete_annotation(pid, aid):
        raise HTTPException(404, "标注不存在")
    return {"ok": True}


# ----------------------------- 三方合并 -----------------------------

@app.post("/api/projects/{pid}/merge", status_code=201)
def api_start_merge(pid: str, body: MergeBody):
    project = db.get_full_project(pid)
    if not project:
        raise HTTPException(404, "项目不存在")
    _, a_annotations = parse_export(body.a, "版本 A")
    _, b_annotations = parse_export(body.b, "版本 B")
    result = three_way_merge(project["annotations"], a_annotations, b_annotations)
    session = db.create_merge_session(
        pid, body.name or f"{project['name']}（合并会话）", result
    )
    return session


@app.get("/api/merges/{mid}")
def api_get_merge(mid: str):
    session = db.get_merge_session(mid)
    if not session:
        raise HTTPException(404, "合并会话不存在")
    session["resolved_count"] = sum(1 for c in session["conflicts"] if c.get("resolution"))
    return session


@app.post("/api/merges/{mid}/resolve")
def api_resolve(mid: str, body: ResolveBody):
    session = db.get_merge_session(mid)
    if not session:
        raise HTTPException(404, "合并会话不存在")
    if session["status"] != "open":
        raise HTTPException(400, "该合并会话已完成")

    conflict = next((c for c in session["conflicts"] if c["id"] == body.conflict_id), None)
    if conflict is None:
        raise HTTPException(404, "冲突项不存在")

    allowed = {"a", "b", "both", "custom"}
    if body.choice not in allowed:
        raise HTTPException(422, "choice 必须是 a / b / both / custom")
    ctype = conflict["type"]
    if ctype == "add_add" and body.choice not in ("a", "b", "both"):
        raise HTTPException(422, "新增冲突只能裁决为 a / b / both")
    if ctype in ("modify_modify", "delete_modify") and body.choice == "both":
        raise HTTPException(422, "该冲突类型不支持 both")
    if body.choice == "custom":
        if ctype != "modify_modify":
            raise HTTPException(422, "仅修改冲突支持自定义内容")
        custom = body.custom or {}
        try:
            start, end = float(custom["start"]), float(custom["end"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(422, "自定义内容需提供合法的 start / end")
        validate_range(start, end)
        custom["start"], custom["end"] = start, end
        body = body.model_copy(update={"custom": custom})

    conflict["resolution"] = {"choice": body.choice, "custom": body.custom}
    db.save_merge_conflicts(mid, session["conflicts"])
    return {"ok": True, "resolved_count": sum(1 for c in session["conflicts"] if c.get("resolution")),
            "total": len(session["conflicts"])}


@app.post("/api/merges/{mid}/finalize", status_code=201)
def api_finalize_merge(mid: str):
    session = db.get_merge_session(mid)
    if not session:
        raise HTTPException(404, "合并会话不存在")
    unresolved = [c["id"] for c in session["conflicts"] if not c.get("resolution")]
    if unresolved:
        raise HTTPException(400, f"尚有冲突未裁决: {', '.join(unresolved)}")
    if session["status"] == "done":
        return {"project_id": session["merged_pid"]}

    base = require_project(session["project_id"])
    try:
        merged_annotations = apply_resolutions(session["auto"], session["conflicts"])
    except ValueError as e:
        raise HTTPException(400, str(e))

    with db.get_conn() as conn:
        segments = db.get_segments(conn, session["project_id"])
    merged = db.create_project(f"{base['name']}（合并结果）")
    db.replace_segments(merged["id"], segments)  # 片段 id 原样复制，标注引用保持有效
    db.replace_annotations(merged["id"], merged_annotations)
    db.finish_merge_session(mid, merged["id"])
    return {"project_id": merged["id"]}


# ----------------------------- 静态前端 -----------------------------

static_dir = os.environ.get("STATIC_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "frontend", "dist"
)
static_dir = os.path.abspath(static_dir)
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

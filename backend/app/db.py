"""SQLite 持久化层（标准库 sqlite3，无需 ORM）。"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable


def db_path() -> str:
    return os.environ.get(
        "DB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app.db"),
    )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    audio_path TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    id         TEXT NOT NULL,
    idx        INTEGER NOT NULL,
    start      REAL NOT NULL,
    end        REAL NOT NULL,
    text       TEXT NOT NULL DEFAULT '',
    speaker    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (project_id, id)
);

CREATE TABLE IF NOT EXISTS annotations (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    id         TEXT NOT NULL,
    segment_id TEXT,
    start      REAL NOT NULL,
    end        REAL NOT NULL,
    speaker    TEXT NOT NULL DEFAULT '',
    topic      TEXT NOT NULL DEFAULT '',
    note       TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, id)
);

CREATE TABLE IF NOT EXISTS merge_sessions (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    auto_json       TEXT NOT NULL,
    conflicts_json  TEXT NOT NULL,
    stats_json      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    merged_pid      TEXT,
    created_at      TEXT NOT NULL
);
"""


def init_db() -> None:
    path = db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------------- projects ----------------

def create_project(name: str) -> dict:
    pid = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
            (pid, name, now()),
        )
    return get_project_meta(pid)


def get_project_meta(pid: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    return dict(row) if row else None


def list_projects() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.*,
                      (SELECT COUNT(*) FROM segments s WHERE s.project_id = p.id)   AS segment_count,
                      (SELECT COUNT(*) FROM annotations a WHERE a.project_id = p.id) AS annotation_count
               FROM projects p ORDER BY p.created_at DESC"""
        ).fetchall()
    return rows_to_dicts(rows)


def delete_project(pid: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))


def set_audio_path(pid: str, path: str | None) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE projects SET audio_path = ? WHERE id = ?", (path, pid))


# ---------------- segments ----------------

def replace_segments(pid: str, segments: list[dict]) -> list[dict]:
    """整批替换转写片段；片段被替换时其上的标注一并清除。"""
    segments = sorted(segments, key=lambda s: float(s.get("start") or 0))
    with get_conn() as conn:
        conn.execute("DELETE FROM annotations WHERE project_id = ?", (pid,))
        conn.execute("DELETE FROM segments WHERE project_id = ?", (pid,))
        out = []
        for idx, s in enumerate(segments):
            sid = s.get("id") or new_id()
            start, end = float(s.get("start") or 0), float(s.get("end") or 0)
            conn.execute(
                "INSERT INTO segments (project_id, id, idx, start, end, text, speaker)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pid, sid, idx, start, end, str(s.get("text") or ""), str(s.get("speaker") or "")),
            )
            out.append(
                {"id": sid, "idx": idx, "start": start, "end": end,
                 "text": s.get("text") or "", "speaker": s.get("speaker") or ""}
            )
    return out


def get_segments(conn, pid: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, idx, start, end, text, speaker FROM segments"
        " WHERE project_id = ? ORDER BY idx",
        (pid,),
    ).fetchall()
    return rows_to_dicts(rows)


# ---------------- annotations ----------------

def list_annotations(conn, pid: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, segment_id, start, end, speaker, topic, note, updated_at"
        " FROM annotations WHERE project_id = ? ORDER BY start, end",
        (pid,),
    ).fetchall()
    return rows_to_dicts(rows)


def get_annotation(conn, pid: str, aid: str) -> dict | None:
    row = conn.execute(
        "SELECT id, segment_id, start, end, speaker, topic, note, updated_at"
        " FROM annotations WHERE project_id = ? AND id = ?",
        (pid, aid),
    ).fetchone()
    return dict(row) if row else None


def create_annotation(pid: str, data: dict) -> dict:
    aid = new_id()
    ts = now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO annotations (project_id, id, segment_id, start, end, speaker, topic, note, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, aid, data.get("segment_id"), float(data["start"]), float(data["end"]),
             data.get("speaker", ""), data.get("topic", ""), data.get("note", ""), ts),
        )
        row = get_annotation(conn, pid, aid)
    return row


def update_annotation(pid: str, aid: str, data: dict) -> dict | None:
    ts = now()
    fields = {k: data[k] for k in ("segment_id", "start", "end", "speaker", "topic", "note") if k in data}
    if "start" in fields:
        fields["start"] = float(fields["start"])
    if "end" in fields:
        fields["end"] = float(fields["end"])
    if not fields:
        with get_conn() as conn:
            return get_annotation(conn, pid, aid)
    set_clause = ", ".join(f"{k} = ?" for k in fields) + ", updated_at = ?"
    params = list(fields.values()) + [ts, pid, aid]
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE annotations SET {set_clause} WHERE project_id = ? AND id = ?", params
        )
        if cur.rowcount == 0:
            return None
        return get_annotation(conn, pid, aid)


def delete_annotation(pid: str, aid: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM annotations WHERE project_id = ? AND id = ?", (pid, aid)
        )
        return cur.rowcount > 0


def replace_annotations(pid: str, annotations: list[dict]) -> None:
    """整批替换标注（用于按导出文件建项目、合并落库），保留原有 id。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM annotations WHERE project_id = ?", (pid,))
        ts = now()
        for a in annotations:
            aid = a.get("id") or new_id()
            conn.execute(
                "INSERT INTO annotations (project_id, id, segment_id, start, end, speaker, topic, note, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pid, aid, a.get("segment_id"), float(a.get("start") or 0), float(a.get("end") or 0),
                 a.get("speaker", "") or "", a.get("topic", "") or "",
                 a.get("note", "") or "", ts),
            )


def get_full_project(pid: str) -> dict | None:
    with get_conn() as conn:
        meta = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        if not meta:
            return None
        project = dict(meta)
        project["has_audio"] = bool(meta["audio_path"])
        project.pop("audio_path", None)
        project["segments"] = get_segments(conn, pid)
        project["annotations"] = list_annotations(conn, pid)
    return project


# ---------------- merge sessions ----------------

def create_merge_session(pid: str, name: str, result: dict) -> dict:
    import json

    mid = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO merge_sessions (id, project_id, name, auto_json, conflicts_json,"
            " stats_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
            (mid, pid, name, json.dumps(result["auto"], ensure_ascii=False),
             json.dumps(result["conflicts"], ensure_ascii=False),
             json.dumps(result["stats"], ensure_ascii=False), now()),
        )
    return {"id": mid, "project_id": pid, "name": name, **result, "status": "open"}


def get_merge_session(mid: str) -> dict | None:
    import json

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM merge_sessions WHERE id = ?", (mid,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "auto": json.loads(row["auto_json"]),
            "conflicts": json.loads(row["conflicts_json"]),
            "stats": json.loads(row["stats_json"]),
            "status": row["status"],
            "merged_pid": row["merged_pid"],
            "created_at": row["created_at"],
        }


def save_merge_conflicts(mid: str, conflicts: list[dict]) -> None:
    import json

    with get_conn() as conn:
        conn.execute(
            "UPDATE merge_sessions SET conflicts_json = ? WHERE id = ?",
            (json.dumps(conflicts, ensure_ascii=False), mid),
        )


def finish_merge_session(mid: str, merged_pid: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE merge_sessions SET status = 'done', merged_pid = ? WHERE id = ?",
            (merged_pid, mid),
        )

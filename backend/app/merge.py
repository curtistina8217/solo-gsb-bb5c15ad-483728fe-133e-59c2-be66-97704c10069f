"""三方合并核心逻辑。

场景：基线项目（base）被导出后，两位编辑各自离线修改并导出版本 A 与 B。
本模块以基线为共同祖先，按「标注 id」与「片段 + 时间区间」识别三类改动：

  - 新增（added）   : 仅出现在 A 或 B 中的标注
  - 修改（modified）: 同一 id 的标注字段与基线不同
  - 删除（deleted） : 基线中存在、某版本中消失的标注

合并规则：
  1. 互不冲突的改动自动合并（单边新增 / 单边修改 / 单边删除 / 双方一致）。
  2. 重叠改动保留双方版本，生成冲突项，要求逐项裁决：
     - modify_modify : 双方以不同方式修改同一标注
     - delete_modify : 一方删除、另一方修改同一标注
     - add_add       : 双方在相同片段上新增了时间区间重叠的标注（按并查集聚类成组）
"""

from __future__ import annotations

FIELDS = ("segment_id", "start", "end", "speaker", "topic", "note")


def _norm_value(key: str, value):
    if key in ("start", "end"):
        try:
            return round(float(value or 0), 3)
        except (TypeError, ValueError):
            return 0.0
    if value is None:
        return None if key == "segment_id" else ""
    return value


def _norm(ann: dict) -> dict:
    return {k: _norm_value(k, ann.get(k)) for k in FIELDS}


def ann_equal(a: dict, b: dict) -> bool:
    """比较两条标注的业务字段是否一致（忽略 id / updated_at 等元数据）。"""
    return _norm(a) == _norm(b)


def intervals_overlap(a: dict, b: dict) -> bool:
    """判断两条标注是否「重叠」：同一片段（或片段未知）且时间区间相交。"""
    sa, sb = a.get("segment_id"), b.get("segment_id")
    if sa and sb and sa != sb:
        return False
    try:
        return float(a["start"]) < float(b["end"]) and float(b["start"]) < float(a["end"])
    except (KeyError, TypeError, ValueError):
        return False


def _conflict(cid: int, ctype: str, base=None, a=None, b=None) -> dict:
    return {
        "id": f"c{cid}",
        "type": ctype,
        "base": base,
        "a": a,
        "b": b,
        "resolution": None,
    }


def three_way_merge(base: list[dict], list_a: list[dict], list_b: list[dict]) -> dict:
    """执行三方合并，返回 {auto, conflicts, stats}。

    auto      : 自动合并后的标注列表
    conflicts : 需要人工裁决的冲突列表（保留双方版本）
    stats     : 自动合并统计
    """
    base_by = {a["id"]: a for a in base if a.get("id")}
    a_by = {a["id"]: a for a in list_a if a.get("id")}
    b_by = {a["id"]: a for a in list_b if a.get("id")}

    auto: list[dict] = []
    conflicts: list[dict] = []
    adds_a: list[dict] = []
    adds_b: list[dict] = []
    stats = {"added": 0, "modified": 0, "deleted": 0, "unchanged": 0}
    cid = 0

    for ann_id in sorted(set(base_by) | set(a_by) | set(b_by)):
        vb, va, vr = base_by.get(ann_id), a_by.get(ann_id), b_by.get(ann_id)

        if vb is not None:
            if va is not None and vr is not None:
                changed_a, changed_b = not ann_equal(va, vb), not ann_equal(vr, vb)
                if not changed_a and not changed_b:
                    auto.append(va)
                    stats["unchanged"] += 1
                elif changed_a and not changed_b:
                    auto.append(va)
                    stats["modified"] += 1
                elif changed_b and not changed_a:
                    auto.append(vr)
                    stats["modified"] += 1
                elif ann_equal(va, vr):  # 双方改成一样
                    auto.append(va)
                    stats["modified"] += 1
                else:
                    cid += 1
                    conflicts.append(_conflict(cid, "modify_modify", base=vb, a=va, b=vr))
            elif va is not None:  # B 删除了该标注
                if ann_equal(va, vb):
                    stats["deleted"] += 1  # A 未动，接受删除
                else:
                    cid += 1
                    conflicts.append(_conflict(cid, "delete_modify", base=vb, a=va, b=None))
            elif vr is not None:  # A 删除了该标注
                if ann_equal(vr, vb):
                    stats["deleted"] += 1
                else:
                    cid += 1
                    conflicts.append(_conflict(cid, "delete_modify", base=vb, a=None, b=vr))
            else:
                stats["deleted"] += 1  # 双方都删除
        else:
            if va is not None and vr is not None:
                # 同一 id 在两边都作为新增出现（极为少见）
                if ann_equal(va, vr):
                    auto.append(va)
                    stats["added"] += 1
                else:
                    cid += 1
                    conflicts.append(_conflict(cid, "add_add", a=[va], b=[vr]))
            elif va is not None:
                adds_a.append(va)
            elif vr is not None:
                adds_b.append(vr)

    # ---- 新增标注的重叠检测：A 的新增与 B 的新增区间重叠则聚类为冲突组 ----
    n, m = len(adds_a), len(adds_b)
    parent = list(range(n + m))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i, x in enumerate(adds_a):
        for j, y in enumerate(adds_b):
            if intervals_overlap(x, y):
                union(i, n + j)

    groups: dict[int, dict[str, list]] = {}
    for i, x in enumerate(adds_a):
        groups.setdefault(find(i), {"a": [], "b": []})["a"].append(x)
    for j, y in enumerate(adds_b):
        groups.setdefault(find(n + j), {"a": [], "b": []})["b"].append(y)

    for g in groups.values():
        if g["a"] and g["b"]:
            cid += 1
            conflicts.append(_conflict(cid, "add_add", a=g["a"], b=g["b"]))
        else:
            for item in g["a"] + g["b"]:
                auto.append(item)
                stats["added"] += 1

    auto.sort(key=lambda x: (float(x.get("start") or 0), float(x.get("end") or 0)))
    return {"auto": auto, "conflicts": conflicts, "stats": stats}


def apply_resolutions(auto: list[dict], conflicts: list[dict]) -> list[dict]:
    """把逐项裁决结果应用到自动合并结果上，得到最终标注列表。

    裁决选项：
      modify_modify : "a" | "b" | "custom"（custom 提供完整字段）
      delete_modify : "a" | "b"（选择某一方即采纳其动作：保留修改 或 删除）
      add_add       : "a" | "b" | "both"
    """
    final = list(auto)
    for c in conflicts:
        r = c.get("resolution")
        if not r:
            raise ValueError(f"冲突 {c['id']} 尚未裁决")
        choice = r.get("choice")
        ctype = c["type"]

        if ctype == "modify_modify":
            if choice == "a":
                final.append(c["a"])
            elif choice == "b":
                final.append(c["b"])
            elif choice == "custom":
                custom = r.get("custom") or {}
                merged = {**c["a"], **{k: v for k, v in custom.items() if k in FIELDS}}
                merged["id"] = c["a"]["id"]
                final.append(merged)
            else:
                raise ValueError(f"冲突 {c['id']} 的裁决选项无效: {choice}")
        elif ctype == "delete_modify":
            # 选择的一方为 None 表示采纳「删除」；否则保留该方的修改版本
            if choice == "a":
                if c.get("a") is not None:
                    final.append(c["a"])
            elif choice == "b":
                if c.get("b") is not None:
                    final.append(c["b"])
            else:
                raise ValueError(f"冲突 {c['id']} 的裁决选项无效: {choice}")
        elif ctype == "add_add":
            if choice == "a":
                final.extend(c["a"])
            elif choice == "b":
                final.extend(c["b"])
            elif choice == "both":
                final.extend(c["a"])
                final.extend(c["b"])
            else:
                raise ValueError(f"冲突 {c['id']} 的裁决选项无效: {choice}")
        else:
            raise ValueError(f"未知冲突类型: {ctype}")

    final.sort(key=lambda x: (float(x.get("start") or 0), float(x.get("end") or 0)))
    return final

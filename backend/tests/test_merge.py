"""三方合并核心逻辑测试。"""

import pytest

from app.merge import apply_resolutions, intervals_overlap, three_way_merge


def ann(aid, start, end, speaker="", topic="", note="", segment_id="s1"):
    return {
        "id": aid,
        "segment_id": segment_id,
        "start": start,
        "end": end,
        "speaker": speaker,
        "topic": topic,
        "note": note,
    }


BASE = [
    ann("a1", 0, 5, speaker="甲", topic="开场", note="基线备注"),
    ann("a2", 10, 15, speaker="乙", topic="提问", note="问题一"),
    ann("a3", 20, 25, speaker="甲", topic="回答", note="回答一"),
]


def test_no_changes_all_unchanged():
    result = three_way_merge(BASE, BASE, BASE)
    assert result["stats"]["unchanged"] == 3
    assert result["conflicts"] == []
    assert len(result["auto"]) == 3


def test_non_overlapping_additions_auto_merged():
    a = BASE + [ann("na", 30, 35, topic="A新增")]
    b = BASE + [ann("nb", 40, 45, topic="B新增")]
    result = three_way_merge(BASE, a, b)
    assert result["stats"]["added"] == 2
    assert result["conflicts"] == []
    ids = {x["id"] for x in result["auto"]}
    assert {"na", "nb"} <= ids


def test_overlapping_additions_become_conflict():
    a = BASE + [ann("na", 30, 36, topic="A新增")]
    b = BASE + [ann("nb", 33, 40, topic="B新增")]
    result = three_way_merge(BASE, a, b)
    assert result["stats"]["added"] == 0
    assert len(result["conflicts"]) == 1
    c = result["conflicts"][0]
    assert c["type"] == "add_add"
    assert [x["id"] for x in c["a"]] == ["na"]
    assert [x["id"] for x in c["b"]] == ["nb"]


def test_additions_on_different_segments_not_overlapping():
    a = BASE + [ann("na", 30, 36, segment_id="s1")]
    b = BASE + [ann("nb", 30, 36, segment_id="s2")]
    result = three_way_merge(BASE, a, b)
    assert result["conflicts"] == []
    assert result["stats"]["added"] == 2


def test_single_side_modify_auto_merged():
    a = [dict(x, note="A修改") if x["id"] == "a1" else x for x in BASE]
    result = three_way_merge(BASE, a, BASE)
    assert result["stats"]["modified"] == 1
    assert result["conflicts"] == []
    assert next(x for x in result["auto"] if x["id"] == "a1")["note"] == "A修改"


def test_both_modify_same_way_auto_merged():
    a = [dict(x, note="相同修改") if x["id"] == "a1" else x for x in BASE]
    b = [dict(x, note="相同修改") if x["id"] == "a1" else x for x in BASE]
    result = three_way_merge(BASE, a, b)
    assert result["conflicts"] == []
    assert next(x for x in result["auto"] if x["id"] == "a1")["note"] == "相同修改"


def test_both_modify_differently_conflict():
    a = [dict(x, note="A版本") if x["id"] == "a1" else x for x in BASE]
    b = [dict(x, note="B版本") if x["id"] == "a1" else x for x in BASE]
    result = three_way_merge(BASE, a, b)
    assert len(result["conflicts"]) == 1
    c = result["conflicts"][0]
    assert c["type"] == "modify_modify"
    assert c["a"]["note"] == "A版本"
    assert c["b"]["note"] == "B版本"
    assert c["base"]["note"] == "基线备注"


def test_delete_vs_unmodified_auto_deleted():
    a = [x for x in BASE if x["id"] != "a2"]  # A 删除 a2
    result = three_way_merge(BASE, a, BASE)
    assert result["stats"]["deleted"] == 1
    assert result["conflicts"] == []
    assert "a2" not in {x["id"] for x in result["auto"]}


def test_delete_vs_modify_conflict():
    a = [x for x in BASE if x["id"] != "a2"]                      # A 删除
    b = [dict(x, topic="B改题") if x["id"] == "a2" else x for x in BASE]  # B 修改
    result = three_way_merge(BASE, a, b)
    assert len(result["conflicts"]) == 1
    c = result["conflicts"][0]
    assert c["type"] == "delete_modify"
    assert c["a"] is None
    assert c["b"]["topic"] == "B改题"


def test_both_deleted_auto():
    a = [x for x in BASE if x["id"] != "a3"]
    b = [x for x in BASE if x["id"] != "a3"]
    result = three_way_merge(BASE, a, b)
    assert result["stats"]["deleted"] == 1
    assert result["conflicts"] == []
    assert "a3" not in {x["id"] for x in result["auto"]}


def test_chained_overlaps_cluster_into_one_conflict():
    a = BASE + [ann("na1", 30, 34), ann("na2", 36, 40)]
    b = BASE + [ann("nb1", 33, 37)]  # 与 na1、na2 都重叠 → 聚成一组
    result = three_way_merge(BASE, a, b)
    assert len(result["conflicts"]) == 1
    c = result["conflicts"][0]
    assert {x["id"] for x in c["a"]} == {"na1", "na2"}
    assert {x["id"] for x in c["b"]} == {"nb1"}


def test_apply_resolutions_choices():
    a = BASE + [ann("na", 30, 36, topic="A新增")]
    b = BASE + [ann("nb", 33, 40, topic="B新增")]
    result = three_way_merge(BASE, a, b)
    conflict = result["conflicts"][0]

    conflict["resolution"] = {"choice": "both"}
    final = apply_resolutions(result["auto"], result["conflicts"])
    assert {"na", "nb"} <= {x["id"] for x in final}

    conflict["resolution"] = {"choice": "a"}
    final = apply_resolutions(result["auto"], result["conflicts"])
    assert "na" in {x["id"] for x in final}
    assert "nb" not in {x["id"] for x in final}


def test_apply_resolution_custom():
    a = [dict(x, note="A版本") if x["id"] == "a1" else x for x in BASE]
    b = [dict(x, note="B版本") if x["id"] == "a1" else x for x in BASE]
    result = three_way_merge(BASE, a, b)
    conflict = result["conflicts"][0]
    conflict["resolution"] = {
        "choice": "custom",
        "custom": {"start": 0, "end": 5, "speaker": "甲", "topic": "开场", "note": "人工合并"},
    }
    final = apply_resolutions(result["auto"], result["conflicts"])
    assert next(x for x in final if x["id"] == "a1")["note"] == "人工合并"


def test_apply_resolution_delete_modify():
    a = [x for x in BASE if x["id"] != "a2"]
    b = [dict(x, topic="B改题") if x["id"] == "a2" else x for x in BASE]
    result = three_way_merge(BASE, a, b)
    conflict = result["conflicts"][0]

    conflict["resolution"] = {"choice": "b"}  # 采纳 B：保留修改
    final = apply_resolutions(result["auto"], result["conflicts"])
    assert "a2" in {x["id"] for x in final}

    conflict["resolution"] = {"choice": "a"}  # 采纳 A：删除
    final = apply_resolutions(result["auto"], result["conflicts"])
    assert "a2" not in {x["id"] for x in final}


def test_unresolved_conflict_raises():
    a = BASE + [ann("na", 30, 36)]
    b = BASE + [ann("nb", 33, 40)]
    result = three_way_merge(BASE, a, b)
    with pytest.raises(ValueError):
        apply_resolutions(result["auto"], result["conflicts"])


def test_intervals_overlap():
    assert intervals_overlap(ann("x", 0, 5), ann("y", 4, 9))
    assert not intervals_overlap(ann("x", 0, 5), ann("y", 5, 9))  # 端点相接不算重叠
    assert not intervals_overlap(ann("x", 0, 5, segment_id="s1"), ann("y", 0, 5, segment_id="s2"))

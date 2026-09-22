import React, { useState } from "react";
import { fmtTime } from "./Timeline.jsx";

export default function AnnotationForm({ segments, annotation, topics, range, onSave, onCancel }) {
  const editing = Boolean(annotation);
  const [form, setForm] = useState({
    start: annotation ? annotation.start : range?.start ?? 0,
    end: annotation ? annotation.end : range?.end ?? 0,
    segment_id: annotation ? annotation.segment_id : null,
    speaker: annotation?.speaker ?? "",
    topic: annotation?.topic ?? "",
    note: annotation?.note ?? "",
  });
  const [err, setErr] = useState("");

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const guessSegment = () => {
    let best = null, bestOverlap = 0;
    for (const s of segments) {
      const overlap = Math.max(0, Math.min(form.end, s.end) - Math.max(form.start, s.start));
      if (overlap > bestOverlap) { best = s; bestOverlap = overlap; }
    }
    return best;
  };

  const segmentId = form.segment_id || guessSegment()?.id || "";
  const submit = (e) => {
    e.preventDefault();
    const start = Number(form.start);
    const end = Number(form.end);
    if (!(start >= 0) || !(end >= 0)) { setErr("时间必须是非负数字"); return; }
    if (end <= start) { setErr("结束时间必须晚于开始时间"); return; }
    onSave({
      start,
      end,
      segment_id: segmentId || null,
      speaker: form.speaker.trim(),
      topic: form.topic.trim(),
      note: form.note.trim(),
    });
  };

  return (
    <form className="panel" onSubmit={submit}>
      <h2>{editing ? "编辑标注" : "新建区间标注"}</h2>
      {!editing && range && (
        <p className="muted">已选取区间 {fmtTime(range.start)} – {fmtTime(range.end)}</p>
      )}
      <div className="grid-2">
        <div>
          <div className="grid-2">
            <div className="field">
              <label>开始（秒）</label>
              <input type="number" step="0.1" min="0" value={form.start}
                onChange={(e) => set("start", e.target.value)} />
            </div>
            <div className="field">
              <label>结束（秒）</label>
              <input type="number" step="0.1" min="0" value={form.end}
                onChange={(e) => set("end", e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label>所属片段（默认按时间自动归属）</label>
            <select value={segmentId} onChange={(e) => set("segment_id", e.target.value)}>
              <option value="">自动归属</option>
              {segments.map((s) => (
                <option key={s.id} value={s.id}>
                  #{s.idx + 1} {fmtTime(s.start)}–{fmtTime(s.end)} {s.speaker}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>说话人</label>
            <input value={form.speaker} onChange={(e) => set("speaker", e.target.value)}
              placeholder="如：受访者 / 记者" />
          </div>
          <div className="field">
            <label>主题</label>
            <input list="topic-list" value={form.topic} onChange={(e) => set("topic", e.target.value)}
              placeholder="如：核心问题" />
            <datalist id="topic-list">
              {topics.map((t) => <option key={t} value={t} />)}
            </datalist>
          </div>
        </div>
        <div className="field">
          <label>备注</label>
          <textarea style={{ minHeight: 150 }} value={form.note}
            onChange={(e) => set("note", e.target.value)}
            placeholder="对该区间的校注说明……" />
        </div>
      </div>
      {err && <p className="error">{err}</p>}
      <div className="row">
        <button className="primary" type="submit">{editing ? "保存修改" : "添加标注"}</button>
        <button type="button" onClick={onCancel}>取消</button>
      </div>
    </form>
  );
}

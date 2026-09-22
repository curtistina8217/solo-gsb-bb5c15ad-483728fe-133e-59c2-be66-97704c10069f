import React, { useState } from "react";
import { api } from "../api.js";
import { fmtTime } from "./Timeline.jsx";

const FIELDS_LABEL = {
  time: "时间区间",
  speaker: "说话人",
  topic: "主题",
  note: "备注",
};

function FieldRow({ label, value, changed }) {
  return (
    <tr>
      <td className="field-name">{label}</td>
      <td className={changed ? "changed" : ""}>{value || <span className="muted">（空）</span>}</td>
    </tr>
  );
}

function annValues(a, segById) {
  return {
    time: `${fmtTime(a.start)}–${fmtTime(a.end)}（${
      segById[a.segment_id] ? "#" + (segById[a.segment_id].idx + 1) : "未归属片段"
    }）`,
    speaker: a.speaker,
    topic: a.topic,
    note: a.note,
  };
}

function diffChanged(baseA, a) {
  if (!baseA) return { time: false, speaker: false, topic: false, note: false };
  return {
    time:
      Math.abs((baseA.start ?? 0) - (a.start ?? 0)) > 0.001 ||
      Math.abs((baseA.end ?? 0) - (a.end ?? 0)) > 0.001 ||
      baseA.segment_id !== a.segment_id,
    speaker: (baseA.speaker || "") !== (a.speaker || ""),
    topic: (baseA.topic || "") !== (a.topic || ""),
    note: (baseA.note || "") !== (a.note || ""),
  };
}

function AnnTable({ ann, segById, baseAnn }) {
  const v = annValues(ann, segById);
  const ch = diffChanged(baseAnn, ann);
  return (
    <table>
      <tbody>
        <FieldRow label={FIELDS_LABEL.time} value={v.time} changed={ch.time} />
        <FieldRow label={FIELDS_LABEL.speaker} value={v.speaker} changed={ch.speaker} />
        <FieldRow label={FIELDS_LABEL.topic} value={v.topic} changed={ch.topic} />
        <FieldRow label={FIELDS_LABEL.note} value={v.note} changed={ch.note} />
      </tbody>
    </table>
  );
}

function SideBox({ title, sideClass, ann, list, segById, baseAnn, deleted }) {
  return (
    <div className={"side " + sideClass + (deleted ? " deleted" : "")}>
      <h4>{title}</h4>
      {deleted && <div>（该方已删除此标注）</div>}
      {ann && <AnnTable ann={ann} segById={segById} baseAnn={baseAnn} />}
      {list && list.map((a, i) => (
        <div key={a.id} style={{ borderTop: i ? "1px dashed #dfe3ea" : "none", paddingTop: 6 }}>
          <AnnTable ann={a} segById={segById} baseAnn={null} />
        </div>
      ))}
    </div>
  );
}

function ConflictCard({ conflict, segById, onResolve }) {
  const res = conflict.resolution;
  const [choice, setChoice] = useState(res?.choice || "");
  const [showCustom, setShowCustom] = useState(res?.choice === "custom");
  const baseA = conflict.base;
  const customBase = conflict.a || conflict.b;
  const [custom, setCustom] = useState(
    () => res?.custom || {
      start: customBase?.start ?? 0,
      end: customBase?.end ?? 0,
      speaker: customBase?.speaker ?? "",
      topic: customBase?.topic ?? "",
      note: customBase?.note ?? "",
    }
  );
  const [err, setErr] = useState("");

  const choose = (c) => {
    setChoice(c);
    setShowCustom(c === "custom");
    if (c !== "custom") onResolve(conflict.id, c);
  };

  const saveCustom = async () => {
    const start = Number(custom.start);
    const end = Number(custom.end);
    if (!(end > start)) { setErr("结束时间必须晚于开始时间"); return; }
    await onResolve(conflict.id, "custom", { ...custom, start, end });
    setErr("");
  };

  const typeLabel = {
    modify_modify: "双方修改了同一标注",
    delete_modify: "一方删除、另一方修改",
    add_add: "双方在重叠区间都新增了标注",
  }[conflict.type];

  const actionText = (ann) =>
    ann === null ? "删除该标注" : ann.topic ? `保留其修改（${ann.topic}）` : "保留其修改";

  return (
    <div className={"conflict-card" + (res ? " resolved" : "")}>
      <div className="row">
        <span className="tag conflict">{conflict.id}</span>
        <b>{typeLabel}</b>
        <span className="spacer" />
        {res ? <span className="ok">✓ 已裁决：{({
          a: "采纳 A", b: "采纳 B", both: "双方保留", custom: "自定义合并",
        })[res.choice]}</span> : <span className="tag conflict">待裁决</span>}
      </div>

      <div className="sides">
        <SideBox
          title={`编辑 A · ${conflict.type === "add_add" ? `新增 ${conflict.a.length} 条` : actionText(conflict.a)}`}
          sideClass="side-a"
          ann={conflict.type !== "add_add" ? conflict.a : null}
          list={conflict.type === "add_add" ? conflict.a : null}
          segById={segById}
          baseAnn={baseA}
          deleted={conflict.a === null}
        />
        <SideBox
          title={`编辑 B · ${conflict.type === "add_add" ? `新增 ${conflict.b.length} 条` : actionText(conflict.b)}`}
          sideClass="side-b"
          ann={conflict.type !== "add_add" ? conflict.b : null}
          list={conflict.type === "add_add" ? conflict.b : null}
          segById={segById}
          baseAnn={baseA}
          deleted={conflict.b === null}
        />
      </div>

      <div className="resolution-box">
        <strong>裁决：</strong>
        {conflict.type === "add_add" ? (
          <>
            <label><input type="radio" name={conflict.id} checked={choice === "a"} onChange={() => choose("a")} /> 采用 A 的新增</label>
            <label><input type="radio" name={conflict.id} checked={choice === "b"} onChange={() => choose("b")} /> 采用 B 的新增</label>
            <label><input type="radio" name={conflict.id} checked={choice === "both"} onChange={() => choose("both")} /> 双方版本都保留</label>
          </>
        ) : conflict.type === "delete_modify" ? (
          <>
            <label><input type="radio" name={conflict.id} checked={choice === "a"} onChange={() => choose("a")} /> 采纳 A 的动作</label>
            <label><input type="radio" name={conflict.id} checked={choice === "b"} onChange={() => choose("b")} /> 采纳 B 的动作</label>
          </>
        ) : (
          <>
            <label><input type="radio" name={conflict.id} checked={choice === "a"} onChange={() => choose("a")} /> 采纳 A 的版本</label>
            <label><input type="radio" name={conflict.id} checked={choice === "b"} onChange={() => choose("b")} /> 采纳 B 的版本</label>
            <label><input type="radio" name={conflict.id} checked={choice === "custom"} onChange={() => choose("custom")} /> 自定义合并…</label>
          </>
        )}

        {showCustom && (
          <div className="panel" style={{ marginTop: 10, marginBottom: 0 }}>
            <div className="grid-2">
              <div className="field">
                <label>开始（秒）</label>
                <input type="number" step="0.1" value={custom.start}
                  onChange={(e) => setCustom({ ...custom, start: e.target.value })} />
              </div>
              <div className="field">
                <label>结束（秒）</label>
                <input type="number" step="0.1" value={custom.end}
                  onChange={(e) => setCustom({ ...custom, end: e.target.value })} />
              </div>
            </div>
            <div className="field">
              <label>说话人</label>
              <input value={custom.speaker} onChange={(e) => setCustom({ ...custom, speaker: e.target.value })} />
            </div>
            <div className="field">
              <label>主题</label>
              <input value={custom.topic} onChange={(e) => setCustom({ ...custom, topic: e.target.value })} />
            </div>
            <div className="field">
              <label>备注</label>
              <textarea value={custom.note} onChange={(e) => setCustom({ ...custom, note: e.target.value })} />
            </div>
            {err && <p className="error">{err}</p>}
            <button className="primary" onClick={saveCustom}>提交自定义裁决</button>
          </div>
        )}
      </div>
    </div>
  );
}

function JsonInput({ title, setDoc, doc }) {
  const [text, setText] = useState("");
  const [err, setErr] = useState("");

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      setText("");
      setDoc(parsed);
      setErr("");
    } catch {
      setErr("文件不是合法 JSON");
    }
  };

  const onText = (v) => {
    setText(v);
    if (!v.trim()) { setDoc(null); return; }
    try {
      setDoc(JSON.parse(v));
      setErr("");
    } catch {
      setErr("JSON 解析中…");
      setDoc(null);
    }
  };

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <h2>{title}</h2>
      <div className="field">
        <label>选择导出的 JSON 文件</label>
        <input type="file" accept=".json,application/json" onChange={onFile} />
      </div>
      <div className="field">
        <label>或直接粘贴导出内容</label>
        <textarea rows={3} value={text} onChange={(e) => onText(e.target.value)}
          placeholder='{"format":"interview-annotator/v1", ...}' />
      </div>
      {doc ? <span className="ok">✓ 已载入：{doc.name || "未命名项目"}</span>
        : err ? <span className="error">{err}</span>
        : <span className="muted">尚未载入</span>}
    </div>
  );
}

export default function MergeView({ project, onBack, onOpenProject, notify }) {
  const [docA, setDocA] = useState(null);
  const [docB, setDocB] = useState(null);
  const [session, setSession] = useState(null);

  const segById = Object.fromEntries(project.segments.map((s) => [s.id, s]));

  const start = async () => {
    if (!docA || !docB) {
      notify("请先载入编辑 A 与编辑 B 的两个导出文件", true);
      return;
    }
    try {
      setSession(await api.startMerge(project.id, docA, docB));
    } catch (e) {
      notify(e.message, true);
    }
  };

  const resolve = async (conflictId, choice, custom) => {
    try {
      await api.resolve(session.id, conflictId, choice, custom);
      setSession(await api.getMerge(session.id));
    } catch (e) {
      notify(e.message, true);
    }
  };

  const finalize = async () => {
    try {
      const { project_id } = await api.finalizeMerge(session.id);
      notify("合并项目已生成");
      onOpenProject(project_id);
    } catch (e) {
      notify(e.message, true);
    }
  };

  const stats = session?.stats;
  const total = session?.conflicts.length || 0;
  const resolved = session?.resolved_count || 0;

  return (
    <div>
      <div className="toolbar">
        <button onClick={onBack}>← 返回项目</button>
        <h1 style={{ margin: 0 }}>三方合并 · {project.name}（基线）</h1>
      </div>

      <div className="panel">
        <b>工作流：</b>
        <ol style={{ margin: "6px 0 0", paddingLeft: 20 }}>
          <li>基线项目（即当前项目）由两位编辑各自通过「导入校注导出」生成离线副本；</li>
          <li>两位编辑离线增删改区间标注后，分别点击「导出校注 JSON」；</li>
          <li>在本页载入 A、B 两份导出文件：互不重叠的改动将自动合并，重叠改动保留双方版本、逐项裁决；</li>
          <li>全部冲突裁决完成后生成合并项目，裁决结果可继续导出。</li>
        </ol>
      </div>

      {!session && (
        <>
          <div className="grid-2">
            <JsonInput title="编辑 A 的导出" setDoc={setDocA} doc={docA} />
            <JsonInput title="编辑 B 的导出" setDoc={setDocB} doc={docB} />
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="primary" onClick={start}>执行三方合并</button>
          </div>
        </>
      )}

      {session && (
        <>
          <div className="panel">
            <div className="row">
              <span className="stat-pill">自动新增 <b>{stats.added}</b></span>
              <span className="stat-pill">自动采用修改 <b>{stats.modified}</b></span>
              <span className="stat-pill">自动删除 <b>{stats.deleted}</b></span>
              <span className="stat-pill">保持不变 <b>{stats.unchanged}</b></span>
              <span className="stat-pill" style={{ background: total ? "#fef3c7" : "#d1fae5" }}>
                待裁决冲突 <b>{total}</b>
              </span>
              <span className="spacer" />
              <span className="muted">已裁决 {resolved}/{total}</span>
            </div>
            {total > 0 && (
              <div className="progress" style={{ marginTop: 8 }}>
                <div style={{ width: `${(resolved / total) * 100}%` }} />
              </div>
            )}
            <details style={{ marginTop: 10 }}>
              <summary className="muted" style={{ cursor: "pointer" }}>
                查看自动合并明细（{session.auto.length} 条）
              </summary>
              <table style={{ marginTop: 6 }}>
                <tbody>
                  {session.auto.map((a) => (
                    <tr key={a.id}>
                      <td style={{ width: 110 }}>{fmtTime(a.start)}–{fmtTime(a.end)}</td>
                      <td>{a.speaker}</td>
                      <td>{a.topic}</td>
                      <td className="muted">{a.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>

          {session.conflicts.map((c) => (
            <ConflictCard
              key={c.id}
              conflict={c}
              segById={segById}
              onResolve={resolve}
            />
          ))}

          {total === 0 && (
            <div className="muted-card" style={{ marginBottom: 14 }}>
              没有重叠改动，所有变更已自动合并，可直接生成合并项目。
            </div>
          )}

          <div className="row">
            <button className="primary" disabled={resolved < total} onClick={finalize}>
              {resolved < total ? `还有 ${total - resolved} 项待裁决` : "生成合并项目"}
            </button>
            {resolved < total && <span className="muted">完成全部冲突裁决后即可生成</span>}
          </div>
        </>
      )}
    </div>
  );
}

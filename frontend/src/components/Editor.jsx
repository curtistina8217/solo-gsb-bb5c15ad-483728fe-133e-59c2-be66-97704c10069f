import React, { useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import Timeline, { fmtTime, topicColor } from "./Timeline.jsx";
import AnnotationForm from "./AnnotationForm.jsx";

export default function Editor({ project, onReload, onBack, onOpenMerge, notify }) {
  const audioRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [audioVersion, setAudioVersion] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const [draftRange, setDraftRange] = useState(null);
  const [editing, setEditing] = useState(null);
  const [activeSegment, setActiveSegment] = useState(null);

  const segById = useMemo(
    () => Object.fromEntries(project.segments.map((s) => [s.id, s])),
    [project.segments]
  );
  const topics = useMemo(
    () => [...new Set(project.annotations.map((a) => a.topic).filter(Boolean))],
    [project.annotations]
  );

  const seek = (t) => {
    setCurrentTime(t);
    if (audioRef.current) {
      audioRef.current.currentTime = t;
    }
    const seg = project.segments.find((s) => t >= s.start && t < s.end);
    setActiveSegment(seg?.id ?? null);
  };

  const saveAnnotation = async (data) => {
    try {
      if (editing) {
        await api.updateAnnotation(project.id, editing.id, data);
      } else {
        await api.createAnnotation(project.id, data);
      }
      setDraftRange(null);
      setEditing(null);
      await onReload();
    } catch (e) {
      notify(e.message, true);
    }
  };

  const removeAnnotation = async (aid) => {
    if (!window.confirm("确定删除该标注？")) return;
    await api.deleteAnnotation(project.id, aid);
    if (selectedId === aid) setSelectedId(null);
    await onReload();
  };

  const onUploadAudio = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await api.uploadAudio(project.id, file);
      setAudioVersion((v) => v + 1);
      notify("音频已上传");
    } catch (err) {
      notify(err.message, true);
    }
  };

  const handleExport = async () => {
    try {
      await download(project);
    } catch (e) {
      notify(e.message, true);
    }
  };

  return (
    <div>
      <div className="toolbar">
        <button onClick={onBack}>← 返回项目列表</button>
        <h1 style={{ margin: 0 }}>{project.name}</h1>
        <span className="spacer" />
        <button onClick={onOpenMerge}>发起三方合并</button>
        <button className="primary" onClick={handleExport}>导出校注 JSON</button>
      </div>

      <div className="panel">
        <div className="row">
          <audio
            ref={audioRef}
            key={audioVersion}
            src={project.has_audio ? `/api/projects/${project.id}/audio?t=${audioVersion}` : undefined}
            controls
            style={{ height: 34 }}
            onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
          />
          {!project.has_audio && <span className="muted">尚未上传音频（可选，不影响校注）</span>}
          <label className="primary" style={{ margin: 0, cursor: "pointer", borderRadius: 6, padding: "6px 14px" }}>
            {project.has_audio ? "替换音频" : "上传访谈音频"}
            <input type="file" accept="audio/*" style={{ display: "none" }} onChange={onUploadAudio} />
          </label>
        </div>
      </div>

      <div className="panel">
        <Timeline
          segments={project.segments}
          annotations={project.annotations}
          currentTime={currentTime}
          selectedId={selectedId}
          onSelectAnnotation={setSelectedId}
          onSeek={seek}
          onCreateRange={(r) => { setDraftRange(r); setEditing(null); setSelectedId(null); }}
        />
      </div>

      {(draftRange || editing) && (
        <AnnotationForm
          segments={project.segments}
          topics={topics}
          range={draftRange}
          annotation={editing}
          onSave={saveAnnotation}
          onCancel={() => { setDraftRange(null); setEditing(null); }}
        />
      )}

      <div className="grid-3">
        <div className="panel">
          <h2>转写片段（{project.segments.length}）</h2>
          <div style={{ maxHeight: 420, overflowY: "auto" }}>
            {project.segments.map((s) => (
              <div
                key={s.id}
                className={"segment-item" + (activeSegment === s.id ? " active" : "")}
                onClick={() => seek(s.start)}
              >
                <div className="segment-meta">
                  #{s.idx + 1}　{fmtTime(s.start)}–{fmtTime(s.end)}　{s.speaker}
                </div>
                <div>{s.text}</div>
              </div>
            ))}
            {project.segments.length === 0 && <div className="muted-card">请先返回列表页导入转写片段</div>}
          </div>
        </div>

        <div className="panel">
          <h2>区间校注（{project.annotations.length}）</h2>
          <div style={{ maxHeight: 420, overflowY: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>说话人</th>
                  <th>主题</th>
                  <th>备注</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {project.annotations.map((a) => (
                  <tr
                    key={a.id}
                    className={"clickable" + (selectedId === a.id ? " selected" : "")}
                    onClick={() => { setSelectedId(a.id); seek(a.start); }}
                  >
                    <td>
                      <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 8,
                        background: topicColor(a.topic), marginRight: 6 }} />
                      {fmtTime(a.start)}–{fmtTime(a.end)}
                      <div className="muted">
                        {segById[a.segment_id] ? `#${segById[a.segment_id].idx + 1}` : "未归属片段"}
                      </div>
                    </td>
                    <td>{a.speaker || "—"}</td>
                    <td>{a.topic ? <span className="tag">{a.topic}</span> : "—"}</td>
                    <td style={{ maxWidth: 240 }}>{a.note || "—"}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button onClick={() => { setEditing(a); setDraftRange(null); }}>编辑</button>{" "}
                      <button className="danger" onClick={() => removeAnnotation(a.id)}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {project.annotations.length === 0 && (
              <div className="muted-card">在上方时间轴拖选一个时间区间即可添加标注</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

async function download(project) {
  const res = await fetch(`/api/projects/${project.id}/export`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${project.name}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

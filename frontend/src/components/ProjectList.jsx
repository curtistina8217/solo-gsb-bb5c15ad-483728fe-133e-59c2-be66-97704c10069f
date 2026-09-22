import React, { useRef, useState } from "react";
import { api } from "../api.js";

export default function ProjectList({ projects, onRefresh, onOpen, notify }) {
  const [name, setName] = useState("");
  const importRef = useRef(null);
  const exportImportRef = useRef(null);

  const create = async () => {
    if (!name.trim()) return;
    const p = await api.createProject(name.trim());
    setName("");
    await onRefresh();
    onOpen(p.id);
  };

  const createDemo = async () => {
    const p = await api.createDemo();
    await onRefresh();
    onOpen(p.id);
  };

  const importTranscript = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      const p = await api.createProject(file.name.replace(/\.json$/i, ""));
      await api.importTranscript(p.id, parsed);
      notify("转写片段已导入");
      await onRefresh();
      onOpen(p.id);
    } catch (err) {
      notify(err.message, true);
    } finally {
      e.target.value = "";
    }
  };

  const importExport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      const p = await api.importExport(data);
      notify("离线副本已创建（标注 id 保持不变，可用于三方合并）");
      await onRefresh();
      onOpen(p.id);
    } catch (err) {
      notify(err.message, true);
    } finally {
      e.target.value = "";
    }
  };

  const remove = async (p) => {
    if (!window.confirm(`确定删除项目「${p.name}」及其全部数据？`)) return;
    await api.deleteProject(p.id);
    await onRefresh();
  };

  return (
    <div>
      <h1>访谈音频校注</h1>
      <p className="muted">
        导入带时间戳的转写片段，在时间轴上拖选区间标注说话人、主题与备注，导出校注 JSON；
        支持双人离线编辑后的三方合并与逐项冲突裁决。
      </p>

      <div className="panel">
        <div className="row">
          <input
            style={{ maxWidth: 260 }}
            placeholder="新项目名称，如：2026-09-22 乡村教育访谈"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <button className="primary" onClick={create}>新建项目</button>
          <button onClick={() => importRef.current?.click()}>导入转写片段 JSON（新建）</button>
          <button onClick={() => exportImportRef.current?.click()}>导入校注导出（离线副本）</button>
          <button onClick={createDemo}>载入示例项目</button>
          <input ref={importRef} type="file" accept=".json" style={{ display: "none" }} onChange={importTranscript} />
          <input ref={exportImportRef} type="file" accept=".json" style={{ display: "none" }} onChange={importExport} />
        </div>
        <p className="muted" style={{ marginBottom: 0, marginTop: 8 }}>
          转写片段格式：<code>{'{"segments":[{"start":0,"end":5.2,"speaker":"记者","text":"……"}]}'}</code>，亦支持裸数组。
        </p>
      </div>

      <div className="panel" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>项目名称</th>
              <th>片段数</th>
              <th>标注数</th>
              <th>创建时间</th>
              <th style={{ width: 120 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id} className="clickable" onClick={() => onOpen(p.id)}>
                <td><b>{p.name}</b></td>
                <td>{p.segment_count}</td>
                <td>{p.annotation_count}</td>
                <td className="muted">{new Date(p.created_at).toLocaleString("zh-CN")}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <button onClick={() => onOpen(p.id)}>打开</button>{" "}
                  <button className="danger" onClick={() => remove(p)}>删除</button>
                </td>
              </tr>
            ))}
            {projects.length === 0 && (
              <tr><td colSpan={5}><div className="muted-card">还没有项目，点击「新建项目」或「载入示例项目」开始</div></td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

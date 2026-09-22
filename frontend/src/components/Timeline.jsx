import React, { useEffect, useMemo, useRef, useState } from "react";

export function fmtTime(t) {
  t = Math.max(0, Number(t) || 0);
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function tickInterval(pxPerSec) {
  const target = 80 / pxPerSec; // 约每 80px 一个刻度
  const candidates = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800];
  return candidates.find((c) => c >= target) || 3600;
}

export function topicColor(topic) {
  let h = 0;
  for (const ch of topic || "") h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h}, 62%, 72%)`;
}

function assignLanes(annotations) {
  const sorted = [...annotations].sort((a, b) => a.start - b.start || a.end - b.end);
  const laneEnds = [];
  return sorted.map((a) => {
    let lane = laneEnds.findIndex((e) => e <= a.start + 0.01);
    if (lane === -1) {
      laneEnds.push(a.end);
      lane = laneEnds.length - 1;
    } else {
      laneEnds[lane] = a.end;
    }
    return { ...a, lane };
  });
}

export default function Timeline({
  segments,
  annotations,
  currentTime,
  selectedId,
  onSelectAnnotation,
  onSeek,
  onCreateRange,
}) {
  const svgRef = useRef(null);
  const [pxPerSec, setPxPerSec] = useState(24);
  const dragRef = useRef(null);
  const [drag, setDrag] = useState(null);

  const duration = useMemo(() => {
    const ends = [...segments.map((s) => s.end), ...annotations.map((a) => a.end), 10];
    return Math.max(...ends) + 1;
  }, [segments, annotations]);

  const width = Math.max(600, duration * pxPerSec);
  const lanes = useMemo(() => assignLanes(annotations), [annotations]);
  const laneCount = Math.max(1, ...lanes.map((a) => a.lane + 1));

  const SEG_Y = 20;
  const SEG_H = 26;
  const ANN_Y = 54;
  const LANE_H = 24;
  const height = ANN_Y + laneCount * LANE_H + 12;

  const interval = tickInterval(pxPerSec);
  const ticks = [];
  for (let t = 0; t <= duration; t += interval) ticks.push(t);

  const timeFromEvent = (e) => {
    const rect = svgRef.current.getBoundingClientRect();
    const t = (e.clientX - rect.left) / pxPerSec;
    return Math.min(Math.max(t, 0), duration);
  };

  useEffect(() => {
    if (!drag) return;
    const onMove = (e) => {
      if (!dragRef.current) return;
      dragRef.current.t1 = timeFromEvent(e);
      setDrag({ ...dragRef.current });
    };
    const onUp = (e) => {
      const d = dragRef.current;
      dragRef.current = null;
      setDrag(null);
      if (!d) return;
      const start = Math.min(d.t0, d.t1);
      const end = Math.max(d.t0, d.t1);
      if (end - start > 0.25) {
        onCreateRange({ start, end });
      } else {
        onSeek(d.t0);
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag, pxPerSec]); // eslint-disable-line react-hooks/exhaustive-deps

  const startDrag = (e) => {
    const t = timeFromEvent(e);
    dragRef.current = { t0: t, t1: t };
    setDrag({ t0: t, t1: t });
  };

  const playheadX = (Number(currentTime) || 0) * pxPerSec;
  const dStart = drag ? Math.min(drag.t0, drag.t1) : 0;
  const dEnd = drag ? Math.max(drag.t0, drag.t1) : 0;

  return (
    <div>
      <div className="toolbar">
        <span className="muted">在时间轴上按住鼠标拖选区间即可添加校注；单击空白处跳转播放位置</span>
        <span className="spacer" />
        <button onClick={() => setPxPerSec((v) => Math.max(4, Math.round(v / 1.5)))}>缩小</button>
        <button onClick={() => setPxPerSec((v) => Math.min(200, Math.round(v * 1.5)))}>放大</button>
        <span className="muted">{pxPerSec} px/s</span>
      </div>
      <div className="timeline-wrap">
        <svg
          ref={svgRef}
          className="timeline-svg"
          width={width}
          height={height}
          onMouseDown={startDrag}
        >
          {/* 刻度尺 */}
          {ticks.map((t) => (
            <g key={t}>
              <line className="tick-line" x1={t * pxPerSec} y1={0} x2={t * pxPerSec} y2={height} />
              <text className="tick-text" x={t * pxPerSec + 3} y={12}>
                {fmtTime(t)}
              </text>
            </g>
          ))}

          {/* 转写片段轨道 */}
          {segments.map((s) => (
            <g key={s.id} onMouseDown={(e) => { e.stopPropagation(); onSeek(s.start); }}>
              <rect
                className="segment-block"
                x={s.start * pxPerSec}
                y={SEG_Y}
                width={Math.max(2, (s.end - s.start) * pxPerSec)}
                height={SEG_H}
                rx={3}
              />
              <text x={s.start * pxPerSec + 5} y={SEG_Y + 17} fontSize={11} fill="#334255">
                {`#${s.idx + 1} ${s.speaker || ""}：${s.text}`.slice(0, Math.max(4, ((s.end - s.start) * pxPerSec - 8) / 6.2))}
              </text>
            </g>
          ))}

          {/* 标注泳道 */}
          {lanes.map((a) => (
            <g key={a.id}>
              <title>{`${fmtTime(a.start)}–${fmtTime(a.end)} ${a.speaker}｜${a.topic}｜${a.note}`}</title>
              <rect
                className={"annotation-block" + (a.id === selectedId ? " selected" : "")}
                x={a.start * pxPerSec}
                y={ANN_Y + a.lane * LANE_H + 2}
                width={Math.max(3, (a.end - a.start) * pxPerSec)}
                height={LANE_H - 6}
                rx={3}
                fill={topicColor(a.topic)}
                onMouseDown={(e) => {
                  e.stopPropagation();
                  onSelectAnnotation(a.id);
                  onSeek(a.start);
                }}
              />
              {(a.end - a.start) * pxPerSec > 24 && (
                <text
                  x={a.start * pxPerSec + 4}
                  y={ANN_Y + a.lane * LANE_H + 15}
                  fontSize={10}
                  fill="#26313d"
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    onSelectAnnotation(a.id);
                  }}
                >
                  {a.topic || a.speaker || "未命名"}
                </text>
              )}
            </g>
          ))}

          {/* 拖拽选区 */}
          {drag && dEnd - dStart > 0.01 && (
            <rect className="drag-rect" x={dStart * pxPerSec} y={SEG_Y}
              width={(dEnd - dStart) * pxPerSec} height={height - SEG_Y - 6} rx={4} />
          )}

          {/* 播放头 */}
          {playheadX > 0 && playheadX <= width && (
            <line className="playhead" x1={playheadX} y1={0} x2={playheadX} y2={height} />
          )}
        </svg>
      </div>
    </div>
  );
}

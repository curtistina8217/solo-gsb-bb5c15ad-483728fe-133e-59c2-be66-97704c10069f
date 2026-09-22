# 访谈音频校注（Interview Annotator）

一个可 Docker 一键启动的访谈音频校注 Web 应用：导入带时间戳的转写片段，在时间轴上拖选区间添加**说话人 / 主题 / 备注**，导出校注 JSON；支持**双人离线编辑后的三方合并**——自动合并不重叠的改动，对重叠改动保留双方版本并要求逐项裁决，裁决结果可继续导出。

- 前端：React 18 + Vite（构建后由后端托管）
- 后端：FastAPI（Python 3.12）
- 存储：本地 SQLite（`/app/data/app.db`，随卷持久化），上传的音频保存在 `/app/data/uploads/`

## 快速开始（Docker，推荐）

```bash
docker compose up --build
```

启动后访问：

- **Web 界面：http://localhost:8000**
- API 文档（Swagger UI）：http://localhost:8000/docs

数据通过名为 `annotator-data` 的卷持久化；删除容器不会丢数据。停止服务：`docker compose down`。

也可以不用 compose 直接构建运行：

```bash
docker build -t interview-annotator .
docker run -p 8000:8000 -v annotator-data:/app/data interview-annotator
```

## 本地开发（不使用 Docker）

需要 Python 3.11+ 与 Node 20+。

```bash
# 后端（端口 8000）
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（端口 5173，/api 自动代理到 8000）
cd frontend
npm install
npm run dev
```

开发时访问 http://localhost:5173 。生产模式下前端构建产物 `frontend/dist` 由 FastAPI 直接托管，单容器即可运行。

运行测试：

```bash
cd backend
python -m pytest tests/ -q
```

## 功能说明

### 1. 导入转写片段

在项目列表页点击「导入转写片段 JSON（新建）」，或在项目内通过 API 导入。格式：

```json
{
  "segments": [
    { "start": 0.0, "end": 6.4, "speaker": "记者", "text": "李老师您好……" },
    { "start": 6.8, "end": 18.2, "speaker": "受访者", "text": "我这几年主要在做……" }
  ]
}
```

也接受裸数组 `[ {...}, ... ]`。`id` 字段可选，缺省时自动生成。重新导入会替换全部片段并清空已有标注。

### 2. 时间轴区间校注

- 时间轴上方为转写片段轨道，下方为标注泳道（按主题着色，自动避让重叠）。
- **按住鼠标拖选**一个时间区间，弹出表单填写说话人、主题、备注；所属片段按重叠时长自动归属，也可手动指定。
- 单击时间轴空白处跳转播放位置；点击片段 / 标注可定位播放。
- 可上传访谈音频（可选），播放头与时间轴联动。
- 「导出校注 JSON」下载当前项目的完整校注（含稳定的片段 / 标注 id）。

### 3. 双人离线编辑 → 三方合并（核心）

```
                ┌────────────┐
                │  基线项目   │  ← 当前项目（共同祖先）
                └─────┬──────┘
          导出 JSON   │   导出 JSON
              ┌───────┴───────┐
              ▼               ▼
        编辑 A 离线副本    编辑 B 离线副本   ← 通过「导入校注导出（离线副本）」创建
              │               │
        离线增删改标注    离线增删改标注
              │               │
          导出 JSON       导出 JSON
              └───────┬───────┘
                      ▼
              三方合并（本应用）
              ├─ 互不重叠 → 自动合并
              └─ 重叠改动 → 保留双方版本，逐项裁决
                      ▼
              合并项目（可再导出）
```

**改动识别**（按标注 id 与「片段 + 时间区间」）：

| 场景 | 处理 |
| --- | --- |
| 仅 A（或仅 B）新增 / 修改 / 删除 | 自动合并 |
| 双方改成相同内容、双方都删除 | 自动合并 |
| 双方以不同方式修改同一标注（`modify_modify`） | 冲突，保留 A / B 两个版本，逐项裁决（可选 A、选 B 或自定义合并内容） |
| 一方删除、另一方修改（`delete_modify`） | 冲突，裁决采纳哪一方的动作 |
| 双方在相同片段上新增**时间区间重叠**的标注（`add_add`，重叠项按连通性聚为一组） | 冲突，裁决采用 A、采用 B 或双方保留 |

操作流程：

1. 打开基线项目 →「发起三方合并」；
2. 分别载入编辑 A、编辑 B 导出的两份 JSON（文件选择或粘贴）；
3. 点击「执行三方合并」，查看自动合并统计与冲突列表；
4. 逐条裁决冲突（进度条显示已裁决数量），全部完成后「生成合并项目」；
5. 合并结果落库为新项目，可继续编辑、再次「导出校注 JSON」。

> 说明：合并以基线项目的转写片段为准，假定 A / B 均由同一基线导出（标注 id 保持稳定）；对片段文本本身的修改不参与合并。

### 导出文件格式

```json
{
  "format": "interview-annotator/v1",
  "project_id": "…",
  "name": "示例：乡村教育访谈",
  "exported_at": "2026-09-22T08:00:00+00:00",
  "segments": [
    { "id": "…", "idx": 0, "start": 0.0, "end": 6.4, "text": "…", "speaker": "记者" }
  ],
  "annotations": [
    {
      "id": "…", "segment_id": "…", "start": 28.0, "end": 41.7,
      "speaker": "受访者", "topic": "核心问题", "note": "师资流失是最突出的矛盾",
      "updated_at": "…"
    }
  ]
}
```

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/projects` | 项目列表 |
| POST | `/api/projects` | 新建项目 |
| GET / DELETE | `/api/projects/{pid}` | 项目详情（含片段与标注）/ 删除 |
| POST | `/api/projects/{pid}/import` | 导入转写片段（替换式） |
| POST | `/api/projects/import_export` | 按导出 JSON 建离线副本（保留 id） |
| GET | `/api/projects/{pid}/export` | 导出校注 JSON |
| POST | `/api/projects/demo` | 创建示例项目 |
| POST / GET | `/api/projects/{pid}/audio` | 上传 / 播放访谈音频 |
| POST | `/api/projects/{pid}/annotations` | 新增区间标注 |
| PUT / DELETE | `/api/projects/{pid}/annotations/{aid}` | 修改 / 删除标注 |
| POST | `/api/projects/{pid}/merge` | 发起三方合并（body: `{a, b}` 两份导出 JSON） |
| GET | `/api/merges/{mid}` | 合并会话（自动结果 + 冲突 + 裁决进度） |
| POST | `/api/merges/{mid}/resolve` | 提交单条冲突裁决 |
| POST | `/api/merges/{mid}/finalize` | 全部裁决后生成合并项目 |

## 目录结构

```
├── Dockerfile              # 多阶段：前端构建 + 后端运行时（单容器）
├── docker-compose.yml      # 一键启动，端口 8000
├── backend/
│   ├── app/
│   │   ├── main.py         # FastAPI 路由
│   │   ├── merge.py        # 三方合并核心算法
│   │   ├── db.py           # SQLite 持久化
│   │   └── seed.py         # 示例数据
│   ├── tests/              # pytest：合并算法 + API 端到端
│   └── requirements.txt
└── frontend/
    └── src/
        ├── App.jsx
        ├── components/
        │   ├── Timeline.jsx        # SVG 时间轴（拖选区间）
        │   ├── Editor.jsx          # 校注编辑页
        │   ├── AnnotationForm.jsx  # 标注表单
        │   ├── MergeView.jsx       # 三方合并与逐项裁决
        │   └── ProjectList.jsx     # 项目列表 / 导入
        └── api.js
```

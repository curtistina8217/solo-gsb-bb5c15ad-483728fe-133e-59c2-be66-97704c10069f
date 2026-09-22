# ---------- 阶段一：构建前端 ----------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 阶段二：后端运行时（同时托管前端静态产物） ----------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/app.db \
    STATIC_DIR=/app/static
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /build/dist ./static

# SQLite 数据与上传的音频都保存在 /app/data，可挂载卷持久化
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

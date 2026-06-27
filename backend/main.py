"""
量子线路划分优化系统 —— FastAPI 后端入口。

启动方式：
    cd backend
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

API 文档：http://localhost:8000/docs
"""

from __future__ import annotations

import os
from pathlib import Path

# 加载 .env 文件（在所有其他导入之前，确保环境变量可用）
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import circuit, partitioning, mapping, export, auth, history, chat

# 创建数据库表
init_db()

app = FastAPI(
    title="量子线路划分优化系统",
    description="""
## 分布式量子计算 —— 量子比特分区与芯片拓扑映射

### 使用流程
1. **注册/登录** — `POST /api/auth/register` / `POST /api/auth/login`
2. **上传电路** — `POST /api/circuit/upload`
3. **分区计算** — `POST /api/partition/run` → 获取 `task_id`
4. **轮询状态** — `GET /api/partition/status/{task_id}`
5. **获取结果** — `GET /api/partition/result/{task_id}`
6. **芯片映射** — `POST /api/mapping/find`
7. **导出报告** — `POST /api/export/report`
    """,
    version="2.0.0",
)

# CORS 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(circuit.router)
app.include_router(partitioning.router)
app.include_router(mapping.router)
app.include_router(export.router)
app.include_router(history.router)
app.include_router(chat.router)


@app.get("/api/health")
def health_check():
    """健康检查"""
    return {"status": "ok", "version": "2.0.0"}

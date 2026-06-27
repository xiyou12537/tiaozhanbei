# 量子线路划分优化系统

分布式量子计算 —— 量子比特分区与芯片拓扑映射系统。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python FastAPI + SQLAlchemy + SQLite |
| 前端 | Vue 3 + Element Plus + Vite |
| 量子计算 | Qiskit + NetworkX |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+ 和 npm

### 1. 克隆项目

```bash
git clone <repo-url>
cd 分布式大系统
```

### 2. 安装 Python 依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 安装核心库和后端依赖
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 3. 配置环境变量

创建 `.env` 文件（参考下方模板）：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-deepseek-api-key
LLM_MODEL=deepseek-chat
```

> 如果没有 DeepSeek API Key，AI 对话功能不可用，但其他功能正常运行。

### 4. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 5. 一键启动

```bash
python run.py
```

这会同时启动：
- 后端：http://localhost:8000（API 文档：http://localhost:8000/docs）
- 前端：http://localhost:5173

也可以分别启动：

```bash
python run.py --backend    # 仅后端
python run.py --frontend   # 仅前端
```

### 6. 使用系统

1. 打开浏览器访问 http://localhost:5173
2. 注册账号（用户名 + 6位以上密码）
3. 登录后上传 QASM 电路文件，进行分区计算和芯片映射

## 项目结构

```
分布式大系统/
├── backend/                  # FastAPI 后端
│   ├── main.py               # 应用入口
│   ├── database.py           # 数据库配置（SQLite）
│   ├── middleware.py          # JWT 认证中间件
│   ├── models.py              # Pydantic 数据模型
│   ├── models_db.py           # SQLAlchemy ORM 模型
│   ├── routers/               # API 路由
│   │   ├── auth.py            # 注册/登录
│   │   ├── circuit.py         # 电路上传
│   │   ├── partitioning.py    # 分区计算
│   │   ├── mapping.py         # 芯片映射
│   │   ├── chat.py            # AI 对话
│   │   ├── export.py          # 导出
│   │   └── history.py         # 历史记录
│   └── services/              # 服务层
├── frontend/                  # Vue 3 前端
│   └── src/
│       ├── views/             # 页面
│       ├── components/        # 组件
│       └── api.js             # Axios + JWT 拦截器
├── quantum_partitioning/      # 量子分区核心算法库
├── my_test/                   # QASM 测试电路
├── data/                      # SQLite 数据库（自动生成）
├── run.py                     # 一键启动脚本
└── .env                       # 环境变量（需自行创建）
```

## 常见问题

### Q: 启动报错 "ModuleNotFoundError: No module named 'xxx'"
A: 确保已安装所有依赖：
```bash
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### Q: 数据库连不上 / 登录失败
A: SQLite 数据库文件在 `data/partitioning.db`，首次启动时会**自动创建**。如果遇到问题：
1. 确保 `data/` 目录存在且有写入权限
2. 删除 `data/partitioning.db` 后重启，系统会重新创建
3. 检查是否安装了 `sqlalchemy>=2.0`

### Q: 前端页面空白
A: 确保执行了 `cd frontend && npm install`，且 Vite 开发服务器正常启动在 5173 端口。

### Q: AI 对话功能不可用
A: 需要在 `.env` 中配置有效的 DeepSeek API Key。没有 Key 不影响其他功能。

## 数据库说明

本项目使用 **SQLite**（本地文件数据库），不需要安装 MySQL/PostgreSQL 等数据库服务器。数据库文件 `data/partitioning.db` 首次启动时自动生成，包含以下表：

- `users` — 用户账号
- `circuits` — 上传的 QASM 电路
- `tasks` — 分区计算任务
- `mappings` — 芯片拓扑映射结果
- `chat_messages` — AI 对话历史

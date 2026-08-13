# 分子量子分布式计算平台

面向小分子量子化学计算与逻辑分布式量子执行证据展示的本地平台。当前产品主线是从分子结构构建 Hamiltonian、执行 VQE、进行量子线路分区与路由，到逻辑虚拟 QPU 模拟及结果验证；不再以旧材料研究业务为产品能力主线。

## 执行边界

所有当前计算任务均使用以下服务端契约：

```text
execution_mode = logical_virtual_qpu
is_real_qpu = false
```

这表示系统执行的是虚拟节点的逻辑分布式模拟，不连接或调度实际量子硬件。Workflow、Molecular Study 和 LiH Bond Scan 的完成状态均不能解释为真实 QPU 执行。

## 当前功能

- 单分子 Workflow：创建分子计算任务，展示分子、Hamiltonian、VQE、分区、映射、路由和逻辑分布式模拟的阶段性证据。
- 计算任务历史：查看已创建的 Workflow，并按任务 ID 恢复结果页。
- Molecular Study 多架构评估：对多个虚拟 QPU 架构进行分区、映射、路由和能量验证对比。
- LiH Bond Scan：提交 LiH 键长扫描，查看离散 HF、VQE、科学验证 VQE 和 FCI 能量曲线、最低点以及部署评估。
- 三类独立验证：
  - 优化器验证：VQE 优化过程、收敛与诊断证据；
  - 科学验证：VQE 与参考能量、粒子数及相关科学诊断；
  - 部署验证：虚拟 QPU 分区、逻辑映射、SWAP 路由、跨 QPU 通信和逻辑分布式模拟证据。

LiH Bond Scan 的部署参考点严格区分三态：`engineering_only_deployment=true` 表示仅工程部署证据，`false` 表示科学验证点部署，`null` 表示尚未记录或尚未形成部署依据；`null` 不等同于 `false`。

## 页面入口

启动并登录后，可从以下前端路由进入产品功能：

| 功能 | 路由 |
| --- | --- |
| 账户中心 | `/auth` |
| 新建分子计算 | `/app/molecules` |
| 计算任务历史 | `/app/molecule-workflows` |
| Workflow 结果 | `/app/molecule-workflows/{workflowId}` |
| 新建 Molecular Study | `/app/molecular-studies/new` |
| Molecular Study 报告 | `/app/molecular-studies/{studyId}` |
| 新建 LiH Bond Scan | `/app/molecular-bond-scans/new` |
| LiH Bond Scan 结果 | `/app/molecular-bond-scans/{scanId}` |
| 模拟能力说明 | `/app/simulation-capabilities` |

## 技术组成

| 层级 | 当前实现 |
| --- | --- |
| 前端 | Vue 3、Vite、Vue Router、Element Plus、ECharts |
| 后端 | Python、FastAPI、SQLAlchemy、SQLite |
| 量子与路由 | Qiskit、NumPy、SciPy、NetworkX，以及仓库内的分区、映射和路由实现 |
| 可选基础设施 | PostgreSQL、Redis、RabbitMQ（开发启动脚本可选择启动） |

## 环境要求

- Python 3.10 或更高版本
- Node.js 18 或更高版本，以及 npm
- 可选：Docker Desktop。生产部署和需要容器化量子化学适配器的环境还需要 Docker。

本地默认可使用 SQLite；不需要 PostgreSQL、Redis 或 RabbitMQ 即可运行同步开发流程。

## 安装与启动

以下命令均以仓库根目录为起点，适用于 Windows PowerShell。

### 1. 创建 Python 环境并安装后端依赖

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

根目录 `requirements.txt` 包含量子计算相关依赖；当本地运行场景需要这些依赖而当前环境尚未安装时，执行：

```powershell
python -m pip install -r requirements.txt
```

### 2. 安装前端依赖

```powershell
Set-Location frontend
npm install
Set-Location ..
```

### 3. 启动本地开发环境

推荐使用仓库提供的启动脚本；它会在后端 `8000`、前端 `5173` 启动服务，并检查健康状态：

```powershell
.\scripts\start-platform-dev.ps1
```

首次运行缺少依赖时，可让脚本安装对应依赖：

```powershell
.\scripts\start-platform-dev.ps1 -InstallBackendDeps -InstallFrontendDeps
```

需要同时启动 PostgreSQL、Redis 与 RabbitMQ，并启动队列 worker 时：

```powershell
.\scripts\start-platform-dev.ps1 -StartInfra
```

启动后访问：

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://127.0.0.1:5173` |
| 后端健康检查 | `http://127.0.0.1:8000/api/health` |
| OpenAPI 文档 | `http://127.0.0.1:8000/docs` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |

## API 概览

除健康检查和 OpenAPI 文档外，业务接口由认证会话保护。实际字段、响应模型和错误语义以运行中服务的 `/openapi.json` 为准。

| API 组 | 主要端点 |
| --- | --- |
| 健康检查 | `GET /api/health` |
| 认证 | `POST /api/auth/register`、`POST /api/auth/login` |
| 单分子 Workflow | `GET /api/molecule-workflows/capabilities`、`POST /api/molecule-workflows`、`GET /api/molecule-workflows`、`GET /api/molecule-workflows/{workflow_id}` |
| Molecular Study | `POST /api/molecular-studies`、`GET /api/molecular-studies/{study_id}` |
| LiH Bond Scan | `GET /api/molecular-bond-scans/capabilities`、`POST /api/molecular-bond-scans`、`GET /api/molecular-bond-scans/{scan_id}` |

创建 Workflow 和 Bond Scan 时，客户端使用 `Idempotency-Key` 保障网络重试不会重复创建同一任务。

## 测试与构建

前端脚本定义在 [`frontend/package.json`](frontend/package.json)。在 `frontend` 目录执行：

```powershell
npm run test:unit
npm run test:e2e
npm run build
```

后端测试位于 `backend/tests/`。在已安装测试依赖的 Python 环境中，从仓库根目录执行：

```powershell
python -m pytest backend/tests
```

前端生产构建输出至 `frontend/dist/`；该目录已由 Git 忽略，不应作为源码提交。

## 部署

生产部署使用 Nginx 提供前端静态构建，并将 `/api`、`/docs`、`/redoc` 和 `/openapi.json` 代理给运行在 `127.0.0.1:8000` 的单个 Uvicorn worker。P1.2 的 SQLite 增量迁移、systemd 单 worker 限制、Nginx 配置与上线前检查均见 [`deploy/README.md`](deploy/README.md)。

部署配置仍遵守本 README 的执行边界：生产环境运行的是 `logical_virtual_qpu` 模拟器，而非真实 QPU。

## 目录结构

```text
backend/                  FastAPI 服务、分子工作流与 API 路由
frontend/                 Vue 前端、页面、服务和浏览器测试
quantum_partitioning/     量子线路分区、映射与路由相关实现
backend/tests/            后端测试
frontend/tests/           前端单元测试
frontend/e2e/             Playwright 端到端测试
docs/                     API、工作流和发布相关文档
deploy/                   Nginx、systemd 与生产部署说明
scripts/                  本地开发启动脚本
```

## 相关文档

- [Molecular Bond Scan API](docs/molecular-bond-scan-api.md)
- [分子分布式量子工作流指南](docs/molecular-distributed-quantum-workflow-guide.md)
- [生产部署说明](deploy/README.md)

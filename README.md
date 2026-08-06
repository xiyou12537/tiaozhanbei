# 量智硫光

面向锂硫电池催化材料筛选的分布式量子-经典协同计算系统。

本系统以锂硫电池多硫化锂转化反应为应用场景，将材料候选库、经典粗筛、量子化学建模、分布式量子线路编译、模拟执行、综合评分和 AI 助手整合到一个可操作的平台中，用于辅助筛选潜在高性能催化材料。

## 系统能做什么

当前版本已经支持以下核心能力：

1. 用户注册、登录与会话管理
2. 多材料候选筛选 workflow
3. 经典粗筛结果展示
4. 量子精修结果展示
5. 材料排行榜与推荐解释
6. 历史筛选任务回看
7. 分布式量子线路分区与芯片映射能力展示
8. AI 助手与知识库检索能力
9. 后端 API 文档与健康检查

当前材料筛选入口以“内置候选材料库”为主，支持从候选材料中选择多个材料进入筛选流程。系统同时支持用户上传材料结构文件，进行结构解析、活性位点确认、Li2Sx 初始吸附构型、局部量子区和模拟器 VQE 建模；真实 DFT 计算须由经批准的外部或本地计算环境完成。

## 适用用户

本系统面向以下使用者：

1. 锂硫电池催化材料研究人员
2. 材料计算与量子化学方向学生
3. 量子计算应用开发人员
4. 需要演示量子-经典协同筛选流程的项目团队
5. 挑战杯、创新创业比赛或科研原型展示场景

## 核心流程

一次标准材料筛选流程如下：

```text
登录系统
-> 进入多材料筛选页面
-> 选择至少 3 个候选材料
-> 创建筛选任务
-> 查看经典粗筛结果
-> 查看量子精修结果
-> 查看材料排行榜
-> 查看推荐理由、风险提示和证据链
-> 在历史页面回看筛选结果
```

系统内部对应的计算链路为：

```text
候选材料输入
-> 经典指标评估
-> 化学模型构建
-> 量子问题编码
-> 分布式量子线路编译
-> 模拟器执行
-> 量子精修评分
-> 综合排序与解释生成
```

## 当前材料筛选说明

当前版本的材料来源主要是后端内置候选材料库，例如：

| 材料 | 类型 | 活性位点 |
| --- | --- | --- |
| Fe-N4/C | 单原子 M-N-C 催化剂 | Fe-N4 |
| Co-N4/C | 单原子 M-N-C 催化剂 | Co-N4 |
| MoS2 | 过渡金属硫化物 | Mo-edge |
| VN | 过渡金属氮化物 | V-top |

这些材料已经内置了用于演示筛选流程的结构化参数和 proxy 指标。用户可以选择多个材料并启动筛选，系统会输出经典粗筛、量子精修、排行榜和推荐解释。

需要注意：

1. 当前版本可以完整演示筛选闭环。
2. 当前内置材料结果主要用于系统流程验证和比赛展示。
3. 当前版本还不是完整 DFT 级别的科研计算平台。
4. 自定义结构可上传、解析、构建局部量子区并接入外部 DFT 导入或 QE/CP2K 直接 DFT Adapter；本地未部署 QE/CP2K 时直接计算接口会明确报告不可用，真实科研结论仍依赖经化学负责人批准的赝势、参数与结果复核。

## 自定义结构科研建模

该能力不是让用户手动填写材料分数，而是让用户上传结构文件，由系统解析并推进可追溯的科研建模工作流。

计划支持的上传文件包括：

| 文件类型 | 示例 |
| --- | --- |
| 分子结构 | `.xyz`, `.mol`, `.sdf` |
| 晶体结构 | `.cif` |
| VASP 结构 | `POSCAR`, `CONTCAR` |
| 计算结果 | `OUTCAR`, `vasprun.xml`, `.log`, `.out` |

当前工作流：

```text
上传材料结构
-> 解析元素、坐标和晶胞
-> 识别或确认活性位点
-> 构建 Li2S6 / Li2S4 初始吸附模型
-> 几何预处理、导入外部 DFT 或提交直接 DFT
-> 确认电荷、自旋、量子区和活性空间
-> 构造 Hamiltonian 并执行模拟器 VQE
-> 输出 Artifact、日志、确认记录和证据链
```

核心文档：

- [FeN4C66 + Li2S4 文献 Benchmark 协议](docs/fe-n4c66-li2s4-benchmark-protocol.md)
- [科研结构建模前后端联调说明](修改意见/已完成/科研结构建模前后端联调说明.md)
- [FeN4C66-Li2S4 文献基准导入任务](修改意见/已完成/后端-FeN4C66-Li2S4文献基准导入任务.md)
- [科研基准案例与 DFT 接入整改需求](修改意见/已完成/后端-科研基准案例与DFT接入整改需求.md)
- [前端科研输入与结构驱动计算结果页需求（已完成）](修改意见/已完成/前端-科研输入确认与结构驱动计算结果页需求.md)
- [前端 FeN4C66-Li2S4 文献基准工作台需求（已完成）](修改意见/已完成/前端-FeN4C66-Li2S4文献基准工作台需求.md)
- [前端科研模型界面去工作流化改版需求](修改意见/待完成/前端-科研模型界面去工作流化改版需求.md)

## 技术架构

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3, Vite, Element Plus, ECharts |
| 后端 | Python, FastAPI, SQLAlchemy, SQLite |
| 量子计算 | Qiskit, NetworkX |
| 知识库 | 文档导入、PDF 解析、检索增强问答 |
| 本地存储 | SQLite |
| 可选基础设施 | PostgreSQL, Redis, RabbitMQ |

## 目录结构

```text
backend/                  FastAPI 后端服务
frontend/                 Vue 前端项目
quantum_partitioning/     量子线路分区与映射核心算法
data/                     本地 SQLite 数据
docs/                     技术文档
scripts/                  启动与辅助脚本
修改意见/                  产品验收、整改和需求文档
README.md                 用户说明书与核心文档入口
```

## 环境要求

建议环境：

1. Windows 10/11
2. Python 3.10 或以上
3. Node.js 18 或以上
4. npm

可选环境：

1. Docker Desktop
2. PostgreSQL
3. Redis
4. RabbitMQ

如果只是本地演示，默认 SQLite 即可，不需要额外安装数据库。

## 快速启动

### 1. 安装 Python 依赖

首次运行前，建议在项目根目录执行：

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r backend\requirements.txt
```

### 2. 安装前端依赖

```powershell
cd frontend
npm install
cd ..
```

### 3. 启动系统

推荐使用平台启动脚本：

```powershell
.\scripts\start-platform-dev.ps1
```

也可以直接双击项目根目录的 `start-system.py`，或在编辑器中运行该文件。启动器会在服务就绪后自动打开前端页面；首次运行时会按需安装缺失的前后端依赖。

如果首次运行发现后端依赖缺失，可以执行：

```powershell
.\scripts\start-platform-dev.ps1 -InstallBackendDeps
```

如果首次运行发现前端依赖缺失，可以执行：

```powershell
.\scripts\start-platform-dev.ps1 -InstallFrontendDeps
```

启动成功后访问：

| 服务 | 地址 |
| --- | --- |
| 前端系统 | `http://127.0.0.1:5173` |
| 后端服务 | `http://127.0.0.1:8000` |
| API 文档 | `http://127.0.0.1:8000/docs` |
| 健康检查 | `http://127.0.0.1:8000/api/health` |

## 用户使用指南

### 1. 注册与登录

打开前端地址：

```text
http://127.0.0.1:5173
```

进入账号页面后：

1. 注册新账号
2. 使用账号密码登录
3. 登录后进入系统工作区

如果访问 `/app` 页面时未登录，系统会自动跳转到登录页。

### 2. 创建材料筛选任务

进入：

```text
/app/screening
```

操作步骤：

1. 在候选材料列表中选择至少 3 个材料
2. 点击启动多材料筛选
3. 等待系统创建 workflow
4. 页面会自动拉取筛选结果

创建成功后，页面会展示：

1. Workflow ID
2. 候选材料数量
3. 推荐材料
4. 联调链路进度

### 3. 查看筛选结果

筛选完成后，可以在当前页面或结果页查看：

1. 材料排行榜
2. 经典粗筛表格
3. 量子精修卡片
4. 推荐理由
5. 风险提示
6. 分数拆解
7. 证据来源说明
8. 下一步验证建议

结果页地址：

```text
/app/results
```

如果 URL 中带有 `workflowId`，系统会打开指定筛选任务：

```text
/app/results?workflowId=<workflow_id>
```

### 4. 查看历史任务

进入：

```text
/app/history
```

历史页面支持查看：

1. 多材料筛选任务
2. 推荐材料
3. 候选材料数量
4. 创建时间
5. 任务状态
6. 重新进入结果页

### 5. 使用知识库和 AI 助手

进入：

```text
/app/knowledge
```

当前知识库能力用于辅助用户理解系统、查询文档和进行基础问答。若配置了大模型 API，AI 助手可以结合知识库内容回答问题。

环境变量示例：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=deepseek-chat
```

如果没有配置 `LLM_API_KEY`，AI 对话能力可能不可用，但登录、筛选、历史记录和基础系统功能仍可使用。

### 6. 查看分布式量子能力

进入：

```text
/app/capability
```

该页面用于展示量子线路分区、芯片映射、通信代价、分布式执行等能力，是本项目连接“材料筛选”和“分布式量子计算”的重要展示模块。

## 后端 API 快速验证

检查后端是否启动：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health
```

注册用户：

```http
POST /api/auth/register
Content-Type: application/json

{
  "username": "demo_user",
  "password": "secret123"
}
```

登录用户：

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "demo_user",
  "password": "secret123"
}
```

获取候选材料：

```http
GET /api/platform/candidates
Authorization: Bearer <token>
```

创建多材料筛选任务：

```http
POST /api/platform/screening-workflows
Authorization: Bearer <token>
Content-Type: application/json

{
  "case_id": "li-s-demo",
  "candidate_materials": ["Fe-N4/C", "Co-N4/C", "MoS2"]
}
```

查询筛选结果：

```http
GET /api/platform/screening-workflows/{workflow_id}
Authorization: Bearer <token>
```

查询排行榜：

```http
GET /api/platform/workflows/{workflow_id}/leaderboard
Authorization: Bearer <token>
```

查询单个材料解释：

```http
GET /api/platform/workflows/{workflow_id}/candidate-explanations/{material_id}
Authorization: Bearer <token>
```

## 当前能力边界

为了避免误解，当前版本需要明确以下边界：

1. 当前筛选材料主要来自内置候选库。
2. 当前部分材料指标属于 demo/proxy 数据，不等同于真实 DFT 计算结果。
3. 当前量子精修以单状态向量模拟器和线路分区规划验证为主，尚未执行分区子线路协同计算、测量重组或连接真实量子硬件。
4. 自定义结构上传筛选正在规划中，尚未作为完整用户功能交付。
5. 系统当前适合本地演示、比赛答辩和流程验证。

## 常见问题

### 前端打不开

优先检查：

1. 是否执行了 `.\scripts\start-platform-dev.ps1`
2. `http://127.0.0.1:5173` 是否返回页面
3. `frontend/node_modules` 是否已安装
4. 端口 `5173` 是否被其他程序占用

### 后端健康检查失败

优先检查：

1. Python 虚拟环境是否可用
2. 后端依赖是否安装完整
3. `http://127.0.0.1:8000/api/health` 是否可访问
4. `.dev-logs/backend.err.log` 是否有错误信息

### 登录注册失败

优先检查：

1. 后端是否启动
2. SQLite 数据库是否可写
3. 前端是否正确代理到 `/api`
4. 用户名是否已存在

### AI 助手不可用

优先检查：

1. `.env` 是否配置 `LLM_API_KEY`
2. `LLM_BASE_URL` 是否可访问
3. 模型名称是否正确
4. 中转 API 是否返回 `401 Unauthorized`

如果出现 `401 Unauthorized`，通常表示 token 无效、API key 错误、额度或中转站鉴权失败。

### 筛选结果看起来像演示数据

这是当前版本的正常边界。当前系统已经打通筛选流程，但真实科研级筛选还需要接入结构上传、DFT/ML 指标计算和更完整的量子化学建模能力。

## 项目文档

项目中已有部分产品和整改文档：

```text
量智硫光-项目方案书.md
量智硫光-核心流程图.md
AI助手RAG需求文档-后端.md
修改意见/待完成/后端自定义结构筛选最终版需求文档.md
```

这些文档用于说明项目方案、核心流程、AI 助手 RAG 能力和下一阶段后端建设方向。

## 建议演示路线

比赛或汇报时建议按以下顺序演示：

```text
首页
-> 注册/登录
-> 多材料筛选
-> 创建筛选任务
-> 查看排行榜
-> 查看材料解释
-> 查看历史记录
-> 展示知识库/AI 助手
-> 展示分布式量子能力
-> 说明最终版自定义结构筛选规划
```

这样可以同时体现：

1. 系统已经可运行
2. 化学筛选链路已经闭环
3. 分布式量子能力已经接入
4. AI 助手和知识库具备扩展空间
5. 自定义结构上传是下一阶段科研级能力方向

## 版本说明

当前 README 对应版本：

```text
量智硫光本地联调验收版
日期：2026-07-08
```

该版本重点说明当前可用功能、启动方式、用户使用流程和最终版建设方向。

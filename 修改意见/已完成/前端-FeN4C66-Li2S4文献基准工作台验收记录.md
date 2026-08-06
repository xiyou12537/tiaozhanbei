# 前端：FeN4C66 + Li2S4 文献基准工作台验收记录

> 验收日期：2026-07-15\
> 最终结论：通过

## 1. 已关闭的条件项

1. `/app/structure-workflows/:workflowId` 已纳入结构工作流顶栏状态源；详情加载后同步 `workflow_id` 与后端真实状态，`literature_reproduction_geometry_ready` 显示为“文献优化几何已就绪”。
2. 新增 Playwright 页面级 E2E，使用真实 Chromium 浏览器覆盖：登录、进入文献基准、加载 2,119 个候选、精确搜索、查看候选 Artifact 元数据、确认创建工作流、跳转详情、检查来源标签、顶栏状态与未开始阶段。

## 2. 自动化验收

```powershell
cd frontend
npm.cmd run test:research-benchmark
npm.cmd run test:e2e:research-benchmark
npm.cmd run build
```

- 展示层单元测试：`4 passed`。
- 页面级 Chromium E2E：`1 passed`。
- Vite 生产构建：通过。

```powershell
python -m pytest backend\tests\test_structure_modeling.py -q
```

- 后端结构建模与文献基准接口回归：`8 passed`。
- 覆盖导入、按 key 发现基准、候选组成校验、候选 Artifact 元数据、候选选择和文献复现工作流创建。

## 3. 科学表达核对

- 候选能量始终标注为源数据原始单位，未表述为吸附能或最终稳定性结论。
- `literature_reproduction_geometry_ready` 未表述为平台独立 DFT 重算完成。
- Hamiltonian、VQE 等未开始阶段明确显示“尚未开始”，未生成占位科研结果。
- 文献复现来源固定显示为“公开文献数据集”和“仅文献复现基线”。

## 4. 非阻塞事项

- Vite 仍报告既有的大 chunk 警告，后续部署优化时处理。
- `npm audit` 报告依赖树存在安全告警；本次未自动执行可能引入破坏性升级的 `npm audit fix --force`。
- Playwright E2E 使用受控接口响应验证前端页面链路；后端真实接口契约由独立的 FastAPI 回归测试覆盖。

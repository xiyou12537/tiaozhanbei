# Fe-N4/C + Li2S4 基准包 v1.0.0

此目录提供可追溯的初始科研输入，不包含虚构的 DFT 能量、优化结构或自旋结论。

## 内容

- `fe-n4c-host.xyz`：含碳边界环境的 Fe-N4/C 局部模型，不是 5 原子 FeN4 调试团簇。
- `li2s4-initial-configurations.json`：Li 端、S 链端和侧向吸附三个独立初始取向。
- `benchmark-case.json`：版本、电荷、自旋候选策略与后续 DFT/VQE 证据链约束。
- `direct-dft-request-template.json`：直接提交 QE 的参数模板。尖括号内容必须由化学负责人替换并记录来源。

## 复现步骤

1. 上传 `fe-n4c-host.xyz` 并创建 `benchmark-case`。
2. 确认 Fe-N4 活性位点，分别生成或导入三个 Li2S4 初始构型。
3. 使用 `POST /api/platform/adsorption-models/{id}/dft-calculations` 提交 QE/CP2K 任务，或使用 `dft-imports` 导入审计完整的外部 DFT 结果。
4. 对每一个 DFT 优化结构执行多自旋候选比较，人工确认可接受解后继续活性空间、Hamiltonian、映射、FCI 和 VQE。

`QE_EXECUTABLE`、`QE_PSEUDO_DIR` 和 `CP2K_EXECUTABLE` 必须在服务端配置。赝势、k 点、自旋设置和收敛阈值必须随任务保存；基准包不会替化学负责人选择唯一自旋态或伪造 DFT 结果。

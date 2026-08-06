# FeN4C66 + Li2S4 文献 Benchmark 协议

## 1. 目的与边界

本协议为“量智硫光”定义唯一的首期科研 benchmark：周期性 `FeN4C66 + Li2S4` 吸附体系。

它采用 Andritsos 与 Rossi 的公开论文和数据集作为参数及输入的唯一事实来源：

- 论文：[10.1002/qua.26956](https://doi.org/10.1002/qua.26956)
- 数据集：[Materials Cloud 2022.48](https://doi.org/10.24435/materialscloud:zz-w3)

该协议分为“文献复现基准”和“平台独立重算”两个阶段。文献数据导入不等于平台已完成真实 DFT；没有完成独立重算和质量门槛前，所有结果只能表述为 `reproduction_baseline_only`。

## 2. 文献模型

| 项目 | 锁定内容 |
| --- | --- |
| 催化剂 | 周期性 FeN4C66 碳载体单原子催化剂 |
| 吸附物 | Li2S4 |
| 计算程序 | CASTEP（文献原始计算） |
| 交换关联泛函 | GGA-PBE |
| 截断能 | 500 eV |
| 色散 | Grimme D2/G06（`sedc_scheme: g06`） |
| k 点 | Monkhorst-Pack `3 x 3 x 1` |
| 真空层 | 表面法向约 18 Å |
| 自旋 | 自旋极化；Fe 初始磁矩 `4.0`；原始 `SPIN_FIX: 2` 必须原样保存 |

`SPIN_FIX: 2` 和 Fe 初始磁矩不是最终自旋多重度的证明。平台不得将它们自动转换为局部团簇的唯一电荷或自旋态。

## 3. 阶段 A：文献复现基准

### 输入

必须从公开数据集导入以下原始文件并校验 MD5：

```text
FeLIPS_data.tar.gz                 e02c63af54a4478722cc82e5754d569f
fe1n4c66-li2s.cell                 1911f4716dab03abf4664145f6221821
fe1n4c66-li2s.param                81f00f321c14eef15bf8847d8a4c7e5c
```

平台还必须计算并保存 SHA-256。所有 `FeN4C66-Li2S4` 候选构型必须保留来源 ID、来源能量、坐标、原始文件哈希和许可证；不得只取第一个候选或按规则摆放替代原始构型。

### 输出状态

```text
data_source: literature_open_dataset
geometry_status: literature_optimized_candidate
scientific_validation_level: reproduction_baseline_only
```

该阶段允许用户选定一个文献候选，进入局部量子区、活性空间、Hamiltonian 和模拟器 VQE 流程；VQE 结果必须标注 `simulator`，不能回写为文献 DFT 重算结果。

## 4. 阶段 B：平台独立 DFT 重算

平台目前只有 Quantum ESPRESSO 与 CP2K Adapter，论文原始计算使用 CASTEP。因此从文献协议迁移到 QE/CP2K 是一次独立重算，必须保留迁移说明与收敛记录，不能声称“完全相同的 CASTEP 复现”。

### 固定工作包

每个 Li2S4 初始候选均需独立执行：

```text
FeN4C66 + Li2S4 吸附体系优化
FeN4C66 宿主单点能
Li2S4 单体单点能
```

三项计算须使用同一软件版本、泛函、赝势/基组、色散、自旋设置、k 点和收敛阈值。仅当这些签名完全一致时，才可计算：

```text
E_ads = E(FeN4C66 + Li2S4) - E(FeN4C66) - E(Li2S4)
```

直接 DFT 任务的最低输入为：PBE、500 eV 等效截断设置、`3 x 3 x 1` k 点、约 18 Å 真空层、色散方案、自旋极化、元素初始磁化、赝势来源与版本、SCF/几何收敛阈值。任何无法从文献原文件确认的设置必须标注为“迁移假设”，附来源或敏感性测试，不得伪装为文献原参数。

## 5. 构型与自旋质量门槛

1. 至少导入并比较文献候选构型；规则生成的 Li 端、S 链端和侧向构型仅可作为补充候选。
2. 每个候选必须完成自旋极化电子结构计算；对局部量子区比较多个合理电荷/自旋候选。
3. SCF 不收敛或自旋污染超过预先记录阈值时，状态必须为 `needs_model_review`，不可进入 VQE。
4. 不允许由最低单次能量自动选择“最终自旋态”；必须保留全部候选、质量指标和接受理由。
5. NEB、反应能垒、溶剂化和真实 QPU 不属于本 benchmark 的验收范围。

## 6. 量子 Benchmark

仅对已通过阶段 B 质量门槛的局部模型执行：

```text
优化结构
-> 量子区与冻结环境记录
-> 确认活性空间
-> PySCF HF 与可行的 CASCI/FCI 参考
-> Fermionic Hamiltonian
-> Parity 或 Jordan-Wigner 映射
-> simulator VQE
-> 与经典参考的绝对误差和相对误差
```

没有经典参考能量时，VQE 只能标注为 `exploratory_simulator_vqe`；有相同活性空间的经典参考后，才可标注为 `benchmark_validated_simulator_vqe`。

## 7. 完成定义

一个完成的 benchmark 必须可追溯到：原始文献文件和哈希、候选构型、全部 DFT 输入输出与版本、三项能量签名、优化结构、自旋候选与质量状态、量子区、活性空间、Hamiltonian、经典参考、VQE 迭代历史和误差。

在此之前，对外统一表述为：

> 系统已接入 FeN4C66 + Li2S4 的公开文献复现基准，并提供结构驱动的模拟器 VQE 流程；独立 DFT 重算与量子误差验证仍在进行。

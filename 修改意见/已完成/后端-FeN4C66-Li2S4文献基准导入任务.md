# 后端：FeN4C66-Li2S4 文献基准导入任务

## 1. 目的

后端已完成结构驱动量子化学闭环原型，但缺少可复现的真实研究输入，导致无法完成最终科研数据验收。

本任务提供一个可立即导入系统的公开文献基准包，用于完成：

```text
文献 Fe-N4-C + Li2S4 构型
-> 外部 DFT 元数据导入
-> 结构驱动局部量子区
-> 活性空间与 Hamiltonian
-> simulator VQE
-> Artifact 和结果追溯
```

该基准仅用于“文献复现与原型验证”，不能自动等同于项目最终科研参数，也不能代替化学负责人审批。

## 2. 公开来源

基准来源：Andritsos 与 Rossi 的 Fe-N4-C 多硫化锂吸附研究。

1. 论文：*Accelerating the theoretical study of Li-polysulfide adsorption on single-atom catalysts via machine learning approaches*，International Journal of Quantum Chemistry，DOI `10.1002/qua.26956`。
2. 开放数据集：Materials Cloud `materialscloud:2022.48`，CC BY 4.0。
3. 数据集页面：<https://archive.materialscloud.org/records/f5t2r-6qf35>
4. 数据集已公开 Fe-N4-C 与 Li2S、Li2S2、Li2S4、Li2S6、Li2S8 的构型和能量数据；其中包含 `FeN4C66-Li2S4` 目录。

来源依据：该研究直接针对 Fe-N4-C 上 Li2Sn（包括 Li2S4）的构型搜索与 DFT 优化，不是泛化的药物或非锂硫体系。

## 3. 可导入文件清单

后端导入任务只使用官方公开文件，下载后必须保存原始文件和校验信息。

| 文件 | 来源 | 用途 |
| --- | --- | --- |
| `FeLIPS_data.tar.gz` | Materials Cloud 数据集 | 包含 `FeN4C66-Li2S4` 候选构型与能量数据 |
| `fe1n4c66-li2s.cell` | Materials Cloud 数据集 | FeN4C66 周期性载体的 CASTEP cell 示例与晶胞设置 |
| `fe1n4c66-li2s.param` | Materials Cloud 数据集 | CASTEP 几何优化计算参数示例 |
| `LiPS-GCH_22_03_1.ipynb` | Materials Cloud 数据集 | 构型筛选流程参考，不要求在平台直接执行 |

已公开的文件校验值：

```text
fe1n4c66-li2s.cell
MD5: 1911f4716dab03abf4664145f6221821

fe1n4c66-li2s.param
MD5: 81f00f321c14eef15bf8847d8a4c7e5c

FeLIPS_data.tar.gz
MD5: e02c63af54a4478722cc82e5754d569f
```

导入后，后端还应计算 SHA-256，作为平台内部 Artifact 哈希。

## 4. 文献计算设置：可直接记录，不可擅自改写

从官方 `fe1n4c66-li2s.param` 读取到以下 CASTEP 参数：

| 参数 | 文献文件中的值 | 平台处理要求 |
| --- | --- | --- |
| 任务 | `GeometryOptimisation` | 原样保存 |
| 交换关联泛函 | `PBE` | 原样保存为 `xc_functional` |
| 平面波截断能 | `500 eV` | 原样保存 |
| 色散修正 | `sedc_apply: true`，`sedc_scheme: g06` | 标注为 Grimme D2/G06 |
| 自旋极化 | `SPIN_POLARIZED: TRUE` | 标注为自旋极化计算 |
| `SPIN_FIX` | `2` | 保存原始值；不得直接解释为自旋多重度 |
| SCF 最大循环 | `160` | 原样保存 |
| 电子能量收敛 | `1e-5` | 原样保存 |
| 力收敛 | `1e-3` | 原样保存 |
| 几何优化算法 | `BFGS` | 原样保存 |

从官方 `fe1n4c66-li2s.cell` 读取到以下体系设置：

| 参数 | 文献文件中的值 | 平台处理要求 |
| --- | --- | --- |
| 晶胞 z 尺寸 | `18.0000000269 Å` | 作为真空层设置记录 |
| k 点网格 | `3 x 3 x 1` | 原样保存 |
| Fe 初始磁矩 | `SPIN=4.0` | 作为初始磁矩记录，不等同于最终自旋态 |
| 载体模型 | FeN4C66 周期性碳载体 | 标记为 `periodic_fe_n4_c66` |

## 5. 重要限制：不得猜测的参数

以下信息不能从现有 `.cell/.param` 示例中可靠推导，后端不得补写为“已确认科研参数”：

1. 最终赝势具体版本和生成细节。
2. Li2S4 最终最低能构型对应的完整 CASTEP 输出与最终自旋解。
3. `SPIN_FIX: 2` 对应的最终物理自旋态或多重度。
4. 文献最佳 Li2S4 构型进入项目局部团簇模型后的总电荷与自旋多重度。
5. 面向项目最终答辩的泛函、色散、赝势和自旋参数是否由化学负责人认可。

因此，系统必须将该案例标记为：

```text
data_source: literature_open_dataset
geometry_status: literature_optimized_candidate
scientific_validation_level: reproduction_baseline_only
```

不得标记为 `chemistry_lead_approved_final_dft`。

## 6. 后端实现要求

### 6.1 文献基准导入

新增受管理员控制的导入能力：

```http
POST /api/platform/research-benchmarks/import-materials-cloud
```

请求示例：

```json
{
  "benchmark_key": "fe-n4-c66-li2s4-literature-v1",
  "dataset_url": "https://archive.materialscloud.org/records/f5t2r-6qf35",
  "source_license": "CC-BY-4.0",
  "adsorbate": "Li2S4",
  "retain_raw_artifacts": true
}
```

实现要求：

1. 下载或由管理员上传官方数据包。
2. 校验公开 MD5；不一致时拒绝导入。
3. 解压后仅读取 `FeN4C66-Li2S4/` 目录中的候选结构和能量文件。
4. 导入原始结构、候选编号、原始能量、单位说明、文件路径和哈希。
5. 不自动将候选能量理解为“最终 DFT 吸附能”；必须保留来源方法和数据集语义。
6. 原始数据、解析数据和派生量子模型均需建立关联。

建议数据对象：

```text
research_benchmark
- benchmark_id
- benchmark_key
- title
- source_url
- source_doi
- source_license
- source_dataset_version
- material_model
- adsorbate
- scientific_validation_level
- status

research_benchmark_artifact
- artifact_id
- benchmark_id
- artifact_role
- original_filename
- checksum_md5
- checksum_sha256
- storage_path
- metadata
```

### 6.2 Li2S4 候选构型选择

`FeLIPS_data.tar.gz` 中的 Li2S4 结构可能包含多个候选构型。后端必须：

1. 导入所有合格候选，不只导入第一个文件或最低编号文件。
2. 保存候选的原始 ID、来源能量、坐标和筛选状态。
3. 根据数据集能量排序可展示“文献候选优先级”，但不能直接视为项目最终最低能构型。
4. 支持用户/管理员选中某一候选作为“文献复现输入”。
5. 将选中构型送入现有活性位点、局部量子区、活性空间和 VQE 流程。

## 7. 从周期性文献模型到 VQE 局部模型

文献模型是 FeN4C66 周期性材料；VQE 不应直接计算整个周期性晶胞。

转换流程：

```text
文献 FeN4C66-Li2S4 周期性构型
-> 选定 Fe-N4 位点与 Li2S4 吸附构型
-> 截取局部反应区
-> 记录冻结环境原子与边界处理
-> 由电子结构 Adapter 计算局部模型候选电荷/自旋
-> 人工确认可接受候选
-> 活性空间
-> Hamiltonian 与 VQE
```

要求：

1. 局部区截取半径、原子列表和冻结环境必须作为 Artifact 保存。
2. 不能把周期性模型的总电荷或 CASTEP 初始磁矩直接当作局部团簇的最终电荷/多重度。
3. 局部模型出现自旋污染或 SCF 不收敛时，正确进入 `needs_model_review`，并保留文献输入与失败日志。
4. 文献复现 VQE 结果默认标记为 `simulator`。

## 8. 验收标准

1. 管理员可以导入公开数据集并通过 MD5 校验。
2. 平台可以看到 `FeN4C66-Li2S4` 的候选结构、来源、能量和许可证。
3. 选择一个候选后，可建立用户不可篡改的文献复现 workflow。
4. 文献参数在界面和 Artifact 中完整可见，且没有被改写为虚构赝势/最终自旋信息。
5. 该 workflow 可进入现有 Hamiltonian 和 simulator VQE 流程，或在电子结构质量不合格时正确停在 `needs_model_review`。
6. 结果页明确写为“文献复现基准”，与化学负责人批准的最终科研数据分开显示。

## 9. 后续升级条件

只有在化学负责人批准以下内容后，才可把文献基准升级为最终科研基准：

1. 最终 Fe-N4-C 结构模型和 Li2S4 吸附构型。
2. DFT 软件和版本。
3. 赝势/ECP 方案。
4. 泛函、色散修正、平面波截断或基组。
5. k 点、真空层和收敛阈值。
6. 自旋极化设置、初始磁矩、最终可接受的自旋解。
7. 吸附能三项能量的同一计算设置。

在此之前，对外表述应为：

```text
系统已接入公开文献 Fe-N4-C/Li2S4 数据包，完成结构驱动量子化学流程的复现基准验证；
最终科研级 DFT 参数与结果仍需经化学负责人确认。
```

## 10. 参考链接

1. [Materials Cloud 开放数据集](https://archive.materialscloud.org/records/f5t2r-6qf35)
2. [论文开放版本与方法说明](https://pmc.ncbi.nlm.nih.gov/articles/PMC9541244/)
3. [论文 DOI](https://doi.org/10.1002/qua.26956)

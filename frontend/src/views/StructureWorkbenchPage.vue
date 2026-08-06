<template>
  <div class="structure-workbench">
    <header class="workbench-head">
      <div>
        <span class="eyebrow">Chemistry Screening &amp; Quantum Execution</span>
        <h2>化学筛选与量子计算</h2>
        <p>从化学结构建模开始，逐步生成量子线路，并为芯片映射、路由和模拟执行准备可追溯输入。</p>
      </div>
      <div class="head-actions">
        <el-tag :type="statusType(structureState.workflowStatus)" effect="dark">
          {{ statusLabel(structureState.workflowStatus) }}
        </el-tag>
        <el-button :disabled="!structureState.workflowId" :loading="isBusy('refreshing_workflow')" @click="handleRefresh">
          刷新状态
        </el-button>
        <el-button @click="handleReset">开始新的分析</el-button>
      </div>
    </header>

    <el-alert
      v-if="structureState.lastError"
      class="global-alert"
      type="error"
      :closable="false"
      :title="structureState.lastError"
      show-icon
    />

    <section class="benchmark-guide">
      <div>
        <span>Public Case Input</span>
        <strong><ChemicalFormula text="Fe-N4 + Li2S4" /> 公开结构案例</strong>
      </div>
      <p>可从公开案例或上传文件开始。Fe-N4 自旋态会随局部配位和吸附环境改变，必须比较可收敛候选，不预设唯一自旋态。</p>
      <el-tag effect="plain">可追溯案例</el-tag>
    </section>

    <div class="workbench-layout">
      <aside class="step-rail">
        <div class="source-badge">
          <span>当前分析</span>
          <strong>{{ structureState.structure?.material_name || '尚未选择结构' }}</strong>
          <small class="mono">{{ shortWorkflowId }}</small>
        </div>
        <nav aria-label="化学筛选与量子计算阶段">
          <section v-for="group in stageGroups" :key="group.name" class="stage-group">
            <h3>{{ group.name }}</h3>
            <ol>
              <li v-for="step in group.steps" :key="step.id" :class="stepClass(step)">
                <button type="button" @click="scrollToStage(step.id)">
                  <span>{{ step.number }}</span>
                  <span>
                    <strong>{{ step.title }}</strong>
                    <small>{{ stepStatus(step) }}</small>
                  </span>
                </button>
              </li>
            </ol>
          </section>
        </nav>
      </aside>

      <main class="stage-stack">
        <section id="stage-structure" class="stage-panel">
          <StageHeading number="01" title="上传并解析结构" status="确认结构来源与解析质量" />
          <div class="two-column">
            <el-form label-position="top" class="research-form">
              <el-form-item label="材料名称" required>
                <el-input v-model="sourceForm.materialName" placeholder="例如 Fe-N4/C" maxlength="100" />
              </el-form-item>
              <el-form-item label="材料类别">
                <el-input v-model="sourceForm.materialFamily" placeholder="例如 single-atom catalyst" maxlength="100" />
              </el-form-item>
              <el-form-item label="研究说明">
                <el-input v-model="sourceForm.description" type="textarea" :rows="2" maxlength="1000" />
              </el-form-item>
              <el-upload
                drag
                :auto-upload="false"
                :limit="1"
                :on-change="handleSourceFileChange"
                :on-remove="handleSourceFileRemove"
              >
                <div class="upload-copy">
                  <strong>选择结构文件</strong>
                  <span>支持 XYZ、CIF、MOL、SDF，最大 20 MB</span>
                </div>
              </el-upload>
              <el-button
                type="primary"
                :loading="isBusy('uploading_source')"
                :disabled="!sourceUploadFile"
                @click="handleUploadSource"
              >
                上传并解析
              </el-button>
            </el-form>

            <div class="evidence-box">
              <template v-if="structureState.structure">
                <div class="box-title">
                  <strong>{{ structureState.structure.material_name }}</strong>
                  <el-tag :type="isStructureValid ? 'success' : 'danger'" effect="plain">
                    {{ structureState.structure.validation?.status }}
                  </el-tag>
                </div>
                <dl class="metadata-grid">
                  <div><dt>化学式</dt><dd><ChemicalFormula :text="structureState.structure.formula" /></dd></div>
                  <div><dt>原子数</dt><dd>{{ structureState.structure.atom_count }}</dd></div>
                  <div><dt>结构类型</dt><dd>{{ structureState.structure.structure_type }}</dd></div>
                  <div><dt>元素</dt><dd>{{ structureState.structure.elements?.join(', ') || '--' }}</dd></div>
                  <div><dt>原始文件</dt><dd>{{ structureState.sourceFileRecord?.original_filename || '--' }}</dd></div>
                  <div><dt>文件类型</dt><dd>{{ structureState.sourceFileRecord?.file_type || '--' }}</dd></div>
                  <div><dt>文件 Hash</dt><dd class="mono">{{ shortHash }}</dd></div>
                  <div><dt>上传时间</dt><dd>{{ formatTime(structureState.sourceFileRecord?.created_at) }}</dd></div>
                  <div><dt>晶胞信息</dt><dd>{{ formatLattice(structureState.structure.lattice) }}</dd></div>
                </dl>
                <ValidationNotes :validation="structureState.structure.validation" />
              </template>
              <div v-else class="empty-copy">
                <strong>尚未解析结构</strong>
                <p>解析成功后会展示组成、原子数、晶格信息以及结构校验意见。</p>
              </div>
            </div>
          </div>
          <el-alert
            v-if="structureState.structure && !isStructureValid"
            type="error"
            :closable="false"
            title="结构校验未通过，只能重新上传或查看错误，后续科研建模已锁定。"
            show-icon
          />
        </section>

        <section id="stage-site" class="stage-panel" :class="{ locked: !isStructureValid }">
          <StageHeading number="02" title="确认活性位点" status="系统建议必须经过研究人员确认" />
          <div class="toolbar-line">
            <el-button
              :disabled="!isStructureValid"
              :loading="isBusy('suggesting_sites')"
              @click="handleSuggestSites"
            >
              获取位点建议
            </el-button>
            <el-radio-group v-model="siteForm.mode" :disabled="!isStructureValid">
              <el-radio-button value="suggested">使用系统建议</el-radio-button>
              <el-radio-button value="manual">手动指定</el-radio-button>
            </el-radio-group>
          </div>

          <div v-if="siteForm.mode === 'suggested'" class="choice-grid">
            <button
              v-for="site in structureState.activeSiteSuggestions"
              :key="site.active_site_id"
              type="button"
              class="choice-card"
              :class="{ selected: siteForm.selectedSiteId === site.active_site_id }"
              @click="selectSuggestedSite(site)"
            >
              <span>{{ site.site_type || 'candidate site' }}</span>
              <strong>{{ site.site_label }}</strong>
              <small>中心原子 {{ formatIndices(site.center_atom_indices) }}</small>
              <small>配位原子 {{ formatIndices(site.neighbor_atom_indices) }} · 配位数 {{ site.neighbor_atom_indices?.length || 0 }}</small>
              <small>方法 {{ site.detection_method }} · 置信度 {{ formatNumber(site.confidence) }}</small>
              <small>{{ activeSiteReason(site) }}</small>
            </button>
            <div v-if="!structureState.activeSiteSuggestions.length" class="empty-inline">点击“获取位点建议”开始分析。</div>
          </div>

          <el-form v-else label-position="top" class="manual-site-form">
            <el-form-item label="位点名称" required><el-input v-model="siteForm.siteLabel" /></el-form-item>
            <el-form-item label="中心原子索引" required><el-input v-model="siteForm.centerIndices" placeholder="例如 0" /></el-form-item>
            <el-form-item label="邻居原子索引"><el-input v-model="siteForm.neighborIndices" placeholder="例如 1, 2, 3, 4" /></el-form-item>
          </el-form>

          <el-input v-model="siteForm.userNote" type="textarea" :rows="2" placeholder="位点确认说明（可选）" />
          <div class="action-row">
            <el-button
              type="primary"
              :disabled="!canConfirmSite"
              :loading="isBusy('confirming_site')"
              @click="handleConfirmSite"
            >
              确认活性位点
            </el-button>
            <span v-if="structureState.confirmedActiveSite" class="confirmed-note">
              已确认 {{ structureState.confirmedActiveSite.site_label }} · {{ identityLabel }} · {{ formatTime(structureState.confirmedActiveSite.confirmation_at) }}。后续模型均基于此位点。
            </span>
          </div>
        </section>

        <section id="stage-adsorption" class="stage-panel" :class="{ locked: !structureState.confirmedActiveSite }">
          <StageHeading number="03" title="选择吸附体系与初始构型" status="初始几何不等于 DFT 优化结果" />
          <div class="input-strip">
            <el-checkbox-group v-model="adsorptionForm.species">
              <el-checkbox value="Li2S4"><ChemicalFormula text="Li2S4" /></el-checkbox>
              <el-checkbox value="Li2S6"><ChemicalFormula text="Li2S6" /></el-checkbox>
            </el-checkbox-group>
            <label>每种构型数 <el-input-number v-model="adsorptionForm.count" :min="3" :max="6" /></label>
            <label>初始距离 (Å) <el-input-number v-model="adsorptionForm.distance" :min="2" :max="3.5" :step="0.1" /></label>
            <el-button
              type="primary"
              :disabled="!structureState.confirmedActiveSite || !adsorptionForm.species.length"
              :loading="isBusy('generating_adsorption')"
              @click="handleGenerateAdsorption"
            >
              生成初始构型
            </el-button>
          </div>
          <el-alert
            type="warning"
            :closable="false"
            title="这些构型只用于建立后续计算输入，尚未经过 DFT 优化，也不代表吸附能。"
            show-icon
          />
          <div class="model-grid">
            <button
              v-for="model in structureState.adsorptionModels"
              :key="model.adsorption_model_id"
              type="button"
              class="model-card"
              :class="{ selected: structureState.selectedAdsorptionModelId === model.adsorption_model_id }"
              @click="selectAdsorptionModel(model.adsorption_model_id)"
            >
              <span class="molecule-mini" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>
              <span><ChemicalFormula :text="model.polysulfide_species" /></span>
              <strong>{{ model.placement_strategy || model.conformation_label || 'Initial conformation' }}</strong>
              <small>距离 {{ formatNumber(model.initial_distance_angstrom) }} Å</small>
              <small>几何质量 {{ formatNumber(model.geometry_quality_score) }} · {{ model.status || '待几何优化' }}</small>
            </button>
          </div>
        </section>

        <section id="stage-geometry" class="stage-panel" :class="{ locked: !selectedAdsorptionModel }">
          <StageHeading number="04" title="确认优化几何或导入 DFT" status="几何来源与计算证据分开记录" />
          <el-radio-group v-model="geometryMode" :disabled="!selectedAdsorptionModel">
            <el-radio-button value="geometry_only">快速几何整理</el-radio-button>
            <el-radio-button value="dft_import">导入外部 DFT</el-radio-button>
          </el-radio-group>

          <div v-if="geometryMode === 'geometry_only'" class="branch-panel">
            <div>
              <strong>Geometry only</strong>
              <p>仅处理明显原子碰撞，不计算总能量或吸附能，不能单独作为科研结论。</p>
            </div>
            <el-button
              type="primary"
              :disabled="!selectedAdsorptionModel"
              :loading="isBusy('preparing_geometry')"
              @click="handlePrepareGeometry"
            >
              生成可计算几何
            </el-button>
          </div>

          <div v-else class="dft-layout">
            <div class="research-form">
              <h4>优化后结构</h4>
              <el-input v-model="optimizedForm.materialName" placeholder="优化后结构名称" />
              <el-upload
                drag
                :auto-upload="false"
                :limit="1"
                :on-change="handleOptimizedFileChange"
                :on-remove="handleOptimizedFileRemove"
              >
                <div class="upload-copy"><strong>选择优化后结构文件</strong><span>需与当前吸附体系原子组成一致</span></div>
              </el-upload>
              <el-button
                :disabled="!optimizedUploadFile"
                :loading="isBusy('uploading_optimized')"
                @click="handleUploadOptimized"
              >
                上传优化结构
              </el-button>
              <el-tag v-if="structureState.optimizedStructure" type="success" effect="plain">
                已解析 {{ structureState.optimizedStructure.formula }}
              </el-tag>
            </div>

            <el-form label-position="top" class="dft-form">
              <el-form-item label="软件 / 版本"><div class="inline-fields"><el-input v-model="dftForm.software" placeholder="Quantum ESPRESSO" /><el-input v-model="dftForm.softwareVersion" placeholder="7.3" /></div></el-form-item>
              <el-form-item label="泛函 / 基组或赝势"><div class="inline-fields"><el-input v-model="dftForm.functional" placeholder="PBE" /><el-input v-model="dftForm.basis" placeholder="PAW" /></div></el-form-item>
              <el-form-item label="色散修正 / 收敛标准"><div class="inline-fields"><el-input v-model="dftForm.dispersion" placeholder="D3" /><el-input v-model="dftForm.convergence" placeholder="force: 0.02 eV/Å" /></div></el-form-item>
              <el-form-item label="总电荷 / 自旋多重度"><div class="inline-fields"><el-input-number v-model="dftForm.totalCharge" :min="-20" :max="20" /><el-input-number v-model="dftForm.spinMultiplicity" :min="1" :max="20" /></div></el-form-item>
              <el-form-item label="初始磁矩或自旋设置说明"><el-input v-model="dftForm.initialMagneticMoments" placeholder="例如 Fe: 4.0 μB，其余原子 0" /></el-form-item>
              <el-form-item label="总能量 (Hartree)"><el-input-number v-model="dftForm.totalEnergy" :precision="8" /></el-form-item>
              <el-form-item label="吸附能分量 (Hartree)"><div class="energy-fields"><el-input-number v-model="dftForm.adsorbedEnergy" placeholder="吸附体系" /><el-input-number v-model="dftForm.hostEnergy" placeholder="材料骨架" /><el-input-number v-model="dftForm.adsorbateEnergy" placeholder="吸附物" /></div></el-form-item>
              <el-checkbox v-model="dftForm.spinPolarization">自旋极化计算</el-checkbox>
              <el-form-item label="日志/输出文件引用"><el-input v-model="dftForm.logReference" placeholder="文件名、Artifact ID 或归档路径" /></el-form-item>
              <el-form-item label="文献 DOI（可选）"><el-input v-model="dftForm.doi" placeholder="10.xxxx/xxxxx" /></el-form-item>
              <el-alert
                v-if="missingDftFields.length"
                type="warning"
                :closable="false"
                :title="`缺少关键科研字段：${missingDftFields.join('、')}。保存后只会标记为计算信息不完整。`"
                show-icon
              />
              <el-button type="primary" :loading="isBusy('importing_dft')" @click="handleImportDft">保存 DFT 证据</el-button>
            </el-form>
          </div>

          <ResultNotice
            v-if="structureState.geometryOptimization"
            title="几何整理已完成"
            :status="structureState.geometryOptimization.source_type"
            :notes="structureState.geometryOptimization.warnings"
          />
          <ResultNotice
            v-if="structureState.dftImport"
            :title="structureState.dftImport.status === 'dft_optimized' ? 'DFT 证据完整' : '导入结构，计算信息不完整'"
            :status="structureState.dftImport.status"
            :notes="structureState.dftImport.comparability_warnings"
          />
        </section>

        <section id="stage-quantum-model" class="stage-panel" :class="{ locked: !canBuildQuantumRegion }">
          <StageHeading number="05" title="确认电荷、自旋与活性空间" status="存在污染或不收敛时必须人工复核" />
          <div class="concept-grid">
            <div><strong>电荷 Charge</strong><p>量子区相对中性体系多出或缺少的电子数。</p></div>
            <div><strong>自旋 Spin</strong><p>未成对电子的组合状态，同一结构可能需要比较多个候选。</p></div>
            <div><strong>活性空间 CAS</strong><p>送入量子算法的关键电子与轨道范围，决定精度和 qubit 数。</p></div>
          </div>

          <div class="region-form">
            <label>量子区半径 (Å)<el-input-number v-model="regionForm.radiusAngstrom" :min="1" :max="12" :step="0.5" /></label>
            <label>初始总电荷<el-input-number v-model="regionForm.totalCharge" :min="-20" :max="20" /></label>
            <label>初始自旋多重度<el-input-number v-model="regionForm.spinMultiplicity" :min="1" :max="20" /></label>
            <el-button type="primary" :disabled="!canBuildQuantumRegion" :loading="isBusy('building_region')" @click="handleBuildRegion">建立量子区</el-button>
          </div>
          <ResultNotice
            v-if="structureState.quantumRegion"
            title="量子区状态"
            :status="statusLabel(structureState.quantumRegion.status)"
            :notes="structureState.quantumRegion.warnings"
          />

          <div class="candidate-control">
            <el-form label-position="top">
              <el-form-item label="电荷候选"><el-input v-model="electronicForm.chargeCandidates" placeholder="0, -1, 1" /></el-form-item>
              <el-form-item label="自旋多重度候选"><el-input v-model="electronicForm.spinMultiplicities" placeholder="1, 3, 5" /></el-form-item>
              <el-form-item label="Basis set"><el-input v-model="electronicForm.basisSet" /></el-form-item>
            </el-form>
            <el-button
              :disabled="structureState.quantumRegion?.status !== 'quantum_region_built'"
              :loading="isBusy('calculating_electronic')"
              @click="handleCalculateElectronic"
            >
              计算电荷与自旋候选
            </el-button>
          </div>

          <div class="table-scroll">
            <table class="research-table">
              <thead><tr><th>来源</th><th>电荷</th><th>多重度</th><th>方法</th><th>SCF</th><th>总能量 (Ha)</th><th>&lt;S²&gt;</th><th>自旋污染</th><th>状态</th><th></th></tr></thead>
              <tbody>
                <tr v-for="candidate in structureState.electronicCandidates" :key="candidate.candidate_id">
                  <td>{{ electronicCandidateSource(candidate) }}</td><td>{{ candidate.total_charge }}</td><td>{{ candidate.spin_multiplicity }}</td><td>{{ candidate.scf_method }}</td>
                  <td>{{ candidate.converged ? '收敛' : '未收敛' }}</td><td>{{ formatNumber(candidate.total_energy_hartree, 6) }}</td>
                  <td>{{ formatNumber(candidate.spin_square_s2, 3) }}</td><td>{{ formatNumber(candidate.spin_contamination_delta, 3) }}</td>
                  <td><el-tag :type="statusType(candidate.quality_status)" effect="plain">{{ statusLabel(candidate.quality_status) }}</el-tag></td>
                  <td><el-button size="small" :disabled="candidate.quality_status !== 'eligible_for_confirmation'" @click="handleConfirmElectronic(candidate.candidate_id)">确认</el-button></td>
                </tr>
                <tr v-if="!structureState.electronicCandidates.length"><td colspan="10" class="empty-cell">尚无电子结构候选</td></tr>
              </tbody>
            </table>
          </div>
          <el-alert
            v-if="hasElectronicReview"
            type="warning"
            :closable="false"
            title="部分候选存在自旋污染或 SCF 未收敛。建议调整初始磁矩、比较 UHF/ROHF、扩大模型或重新检查量子区。"
            show-icon
          />

          <div class="action-row">
            <el-button
              :disabled="!structureState.confirmedElectronicCandidate"
              :loading="isBusy('calculating_active_spaces')"
              @click="handleCalculateActiveSpaces"
            >
              生成活性空间候选
            </el-button>
            <span v-if="structureState.confirmedElectronicCandidate" class="confirmed-note">电荷与自旋候选已确认</span>
          </div>

          <div class="active-space-grid">
            <article v-for="space in structureState.activeSpaceCandidates" :key="space.active_space_id" class="active-space-card">
              <div><span>Active Space</span><strong>CAS({{ space.active_electrons }}, {{ space.active_orbitals }})</strong></div>
              <dl>
                <div><dt>预计 Qubits</dt><dd>{{ space.active_orbitals * 2 }}</dd></div>
                <div><dt>状态</dt><dd>{{ statusLabel(space.status) }}</dd></div>
              </dl>
              <p>{{ space.selection_reason }}</p>
              <small>轨道贡献：{{ orbitalContributionLabel(space) }}</small>
              <small>资源风险：{{ activeSpaceRiskLabel(space) }}</small>
              <el-button size="small" :disabled="space.status === 'needs_model_review'" @click="handleConfirmActiveSpace(space.active_space_id)">确认活性空间</el-button>
            </article>
          </div>
        </section>

        <section id="stage-circuit" class="stage-panel" :class="{ locked: !canRunVqe }">
          <StageHeading number="06" title="Hamiltonian 与量子线路" status="将化学问题编码为可追溯的 VQE 线路" />
          <div class="quantum-config">
            <label>Hamiltonian 编码<el-select v-model="quantumForm.mappingMethod"><el-option label="Parity" value="parity" /><el-option label="Jordan-Wigner" value="jordan_wigner" /></el-select></label>
            <label>Ansatz 层数<el-input-number v-model="quantumForm.ansatzLayers" :min="1" :max="4" /></label>
            <label>Shots<el-input-number v-model="quantumForm.shots" :min="1" :step="1024" /></label>
            <label>最大迭代<el-input-number v-model="quantumForm.maxIterations" :min="1" :max="500" /></label>
            <el-checkbox v-model="quantumForm.enableZ2Tapering">Z2 tapering</el-checkbox>
            <el-button type="primary" :disabled="!canRunVqe" :loading="isBusy('running_vqe')" @click="handleRunQuantum">生成线路并运行基准求解</el-button>
          </div>
          <div v-if="!structureState.quantumResult" class="empty-evidence">
            <strong>尚未生成 Hamiltonian 和量子线路</strong>
            <p>先确认活性空间，再生成真实的 qubit、Pauli 项和 QASM 产物。</p>
          </div>
          <div v-else class="quantum-results">
            <article><span>Hamiltonian</span><strong>{{ structureState.quantumResult.fermionic.method_name }}</strong><small>{{ structureState.quantumResult.fermionic.basis_set }}</small></article>
            <article><span>Hamiltonian 编码</span><strong>{{ structureState.quantumResult.qubit.qubit_count }} qubits</strong><small>{{ structureState.quantumResult.qubit.pauli_term_count }} Pauli terms</small></article>
            <article><span>VQE 线路</span><strong>{{ structureState.quantumResult.circuit.parameter_count }} parameters</strong><small>OpenQASM {{ structureState.quantumResult.circuit.openqasm_version || '2.0' }}</small></article>
            <article><span>基准求解</span><strong>{{ formatNumber(structureState.quantumResult.execution.final_energy_hartree, 8) }} Ha</strong><small>{{ executionBackendLabel }}，非芯片路由后结果</small></article>
          </div>
          <div v-if="structureState.quantumResult" class="quantum-detail-grid">
            <dl>
              <div><dt>结构 / 量子区 / 活性空间</dt><dd class="mono">{{ structureState.structure?.structure_id }} / {{ structureState.quantumRegion?.quantum_region_id }} / {{ structureState.confirmedActiveSpace?.active_space_id }}</dd></div>
              <div><dt>Hamiltonian 编码方法</dt><dd>{{ structureState.quantumResult.qubit.mapping_method }} · Z2 {{ structureState.quantumResult.qubit.z2_tapering_applied ? '已裁剪' : '未裁剪' }}</dd></div>
              <div><dt>映射前后 Qubits</dt><dd>{{ structureState.quantumResult.qubit.qubit_count_before_tapering }} → {{ structureState.quantumResult.qubit.qubit_count }}</dd></div>
              <div><dt>Pauli / 截断误差</dt><dd>{{ structureState.quantumResult.qubit.pauli_term_count }} / {{ formatNumber(structureState.quantumResult.qubit.truncation_error_estimate, 8) }}</dd></div>
            </dl>
            <dl>
              <div><dt>Ansatz / 层数</dt><dd>hardware_efficient_ry_cx / {{ quantumForm.ansatzLayers }}</dd></div>
              <div><dt>优化器 / 收敛阈值</dt><dd>COBYLA / {{ quantumForm.convergenceTolerance }}</dd></div>
              <div><dt>Shots / 收敛</dt><dd>{{ structureState.quantumResult.execution.shots_total }} / {{ structureState.quantumResult.execution.converged ? '是' : '否' }}</dd></div>
              <div><dt>能量不确定度</dt><dd>{{ formatNumber(structureState.quantumResult.execution.energy_uncertainty_hartree, 8) }} Ha</dd></div>
            </dl>
          </div>
          <el-alert
            v-if="structureState.quantumResult"
            type="info"
            :closable="false"
            title="当前能量来自单一 statevector 模拟器的基准求解，不是芯片映射、路由后的执行结果。"
            show-icon
          />
        </section>

        <section id="stage-grouping" class="stage-panel" :class="{ locked: !structureState.quantumResult }">
          <StageHeading number="07" title="量子线路分组" status="拆分子线路并评估跨分组通信代价" />
          <div v-if="distributedPlan" class="execution-summary-grid">
            <article>
              <span>分组状态</span>
              <strong>{{ groupingCapabilityLabel }}</strong>
              <small>{{ distributedPlan.partition_method || '未返回方法' }}</small>
            </article>
            <article>
              <span>子线路</span>
              <strong>{{ distributedPlan.subcircuits?.length || 0 }}</strong>
              <small>当前仅形成分组规划</small>
            </article>
            <article>
              <span>跨组传态</span>
              <strong>{{ distributedPlan.teleportations ?? '--' }}</strong>
              <small>用于评估通信成本</small>
            </article>
            <article>
              <span>实际分布式执行</span>
              <strong>{{ distributedPlan.actual_distributed_execution ? '已执行' : '未执行' }}</strong>
              <small>不将规划结果表述为真实 QPU 执行</small>
            </article>
          </div>
          <div v-else class="empty-evidence">
            <strong>尚未生成可分组的量子线路</strong>
            <p>完成 Hamiltonian 编码和 VQE 线路生成后，这里将展示子线路和跨组通信信息。</p>
          </div>
          <div v-if="distributedPlan?.subcircuits?.length" class="subcircuit-list">
            <article v-for="subcircuit in distributedPlan.subcircuits" :key="subcircuit.index">
              <span>子线路 {{ Number(subcircuit.index) + 1 }}</span>
              <strong>Qubits {{ subcircuit.qubits?.join(', ') || '--' }}</strong>
              <small>{{ subcircuit.assignment_status === 'planned_not_executed' ? '已规划，未执行' : (subcircuit.assignment_status || '待确认') }}</small>
            </article>
          </div>
        </section>

        <section id="stage-chip-mapping" class="stage-panel capability-pending" :class="{ locked: !distributedPlan }">
          <StageHeading number="08" title="映射到目标芯片" status="将逻辑量子比特或子线路分配到具体设备" />
          <div class="capability-form-grid">
            <label>目标芯片
              <el-select model-value="" disabled placeholder="尚未接入芯片目录" />
            </label>
            <label>映射目标
              <el-select model-value="minimum_communication" disabled><el-option label="优先降低跨芯片通信" value="minimum_communication" /></el-select>
            </label>
            <label>芯片拓扑
              <el-input model-value="等待设备能力接口" disabled />
            </label>
            <el-button type="primary" disabled>计算芯片映射</el-button>
          </div>
          <CapabilityBoundary
            title="当前分析链路尚未接入芯片映射"
            description="页面已预留目标芯片、芯片拓扑和映射策略输入。后端返回真实设备与映射结果前，不生成 QPU 分配。"
          />
        </section>

        <section id="stage-routing" class="stage-panel capability-pending">
          <StageHeading number="09" title="芯片拓扑路由" status="选择物理量子比特，并生成符合芯片耦合约束的线路" />
          <div class="capability-form-grid">
            <label>初始布局<el-select model-value="automatic" disabled><el-option label="自动选择" value="automatic" /></el-select></label>
            <label>路由策略<el-select model-value="sabre" disabled><el-option label="SABRE" value="sabre" /></el-select></label>
            <label>优化级别<el-input-number :model-value="2" :min="0" :max="3" disabled /></label>
            <el-button type="primary" disabled>生成路由后线路</el-button>
          </div>
          <div class="expected-output-grid">
            <span>物理量子比特布局</span><span>SWAP 数量</span><span>路由前后深度</span><span>路由后 QASM</span>
          </div>
          <CapabilityBoundary
            title="芯片路由后端尚未实现"
            description="当目标芯片和逻辑映射就绪后，此阶段应返回初始布局、SWAP 插入、路由前后门数与深度，以及可下载的路由后线路。"
          />
        </section>

        <section id="stage-simulation" class="stage-panel capability-pending">
          <StageHeading number="10" title="路由后模拟执行" status="执行符合目标芯片约束的线路，并回传可审计结果" />
          <div class="capability-form-grid">
            <label>执行后端<el-select model-value="routed_simulator" disabled><el-option label="路由线路模拟器" value="routed_simulator" /></el-select></label>
            <label>Shots<el-input-number :model-value="8192" :min="1" disabled /></label>
            <label>噪声模型<el-select model-value="device_calibrated" disabled><el-option label="设备标定噪声" value="device_calibrated" /></el-select></label>
            <el-button type="primary" disabled>开始模拟执行</el-button>
          </div>
          <div class="expected-output-grid">
            <span>测量计数</span><span>能量与不确定度</span><span>成功率 / Fidelity</span><span>执行时间与日志</span>
          </div>
          <CapabilityBoundary
            title="路由后模拟执行接口尚未实现"
            description="当前 VQE 基准能量来自未经芯片路由的 statevector 模拟。这里将只接收路由后线路的真实模拟结果，两者不会混用。"
          />
        </section>

        <section id="stage-evidence" class="stage-panel evidence-summary">
          <StageHeading number="11" title="筛选结果与证据" status="汇总化学建模、量子线路与芯片执行的可追溯产物" />
          <div class="evidence-timeline">
            <div :class="{ complete: structureState.structure }"><span>结构证据</span><strong>{{ structureState.structure ? '已解析并溯源' : '待上传' }}</strong></div>
            <div :class="{ complete: structureState.dftImport?.status === 'dft_optimized' }"><span>DFT 证据</span><strong>{{ dftEvidenceLabel }}</strong></div>
            <div :class="{ complete: structureState.confirmedElectronicCandidate }"><span>电子结构</span><strong>{{ structureState.confirmedElectronicCandidate ? '已人工确认' : '待确认' }}</strong></div>
            <div :class="{ complete: structureState.quantumResult }"><span>量子基准</span><strong>{{ structureState.quantumResult ? executionBackendLabel : '待生成' }}</strong></div>
          </div>
          <div class="scope-box">
            <div><span>当前结论强度</span><strong>{{ evidenceStrength }}</strong></div>
            <div><span>可用范围</span><strong>{{ resultScope }}</strong></div>
            <p>{{ nextStepAdvice }}</p>
          </div>
          <div class="artifact-list">
            <strong>Artifacts</strong>
            <span v-for="artifact in artifactItems" :key="artifact.id"><i>{{ artifact.type }}</i><b class="mono">{{ artifact.id }}</b></span>
            <small v-if="!artifactItems.length">后端尚未生成可追踪 Artifact。</small>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ChemicalFormula from '../components/ChemicalFormula.vue'
import { useAuth } from '../composables/useAuth'
import { useStructureWorkflow } from '../composables/use-structure-workflow'

const {
  structureState,
  isStructureValid,
  selectedAdsorptionModel,
  canBuildQuantumRegion,
  canRunVqe,
  uploadSourceStructure,
  uploadOptimizedStructure,
  requestActiveSiteSuggestions,
  confirmActiveSite,
  createAdsorptionConformations,
  selectAdsorptionModel,
  prepareGeometry,
  importDftEvidence,
  buildQuantumRegion,
  calculateElectronicCandidates,
  confirmElectronicCandidate,
  calculateActiveSpaces,
  confirmActiveSpaceCandidate,
  executeQuantumCalculation,
  refreshWorkflow,
  resetWorkflow,
} = useStructureWorkflow()
const { username } = useAuth()

const sourceUploadFile = ref(null)
const optimizedUploadFile = ref(null)
const geometryMode = ref('geometry_only')

const sourceForm = reactive({ materialName: '', materialFamily: '', description: '' })
const optimizedForm = reactive({ materialName: '优化后吸附结构' })
const siteForm = reactive({ mode: 'suggested', selectedSiteId: '', siteLabel: '', centerIndices: '', neighborIndices: '', userNote: '' })
const adsorptionForm = reactive({ species: ['Li2S4'], count: 3, distance: 2.6 })
const regionForm = reactive({ radiusAngstrom: 5, totalCharge: 0, spinMultiplicity: 1 })
const electronicForm = reactive({ chargeCandidates: '0, -1, 1', spinMultiplicities: '1, 3, 5', basisSet: 'def2-svp' })
const dftForm = reactive({
  software: '', softwareVersion: '', functional: '', basis: '', dispersion: '', convergence: '',
  totalCharge: 0, spinMultiplicity: 1, totalEnergy: null, spinPolarization: true,
  initialMagneticMoments: '', logReference: '', doi: '', adsorbedEnergy: null, hostEnergy: null, adsorbateEnergy: null,
})
const quantumForm = reactive({ mappingMethod: 'parity', enableZ2Tapering: true, pauliCoefficientCutoff: 0.000001, ansatzLayers: 1, maxIterations: 200, convergenceTolerance: 0.0001, shots: 8192 })

const stageGroups = [
  {
    name: '化学结构',
    steps: [
      { id: 'stage-structure', number: '01', title: '结构输入', state: 'structure' },
      { id: 'stage-site', number: '02', title: '活性位点', state: 'site' },
      { id: 'stage-adsorption', number: '03', title: '吸附构型', state: 'adsorption' },
      { id: 'stage-geometry', number: '04', title: '几何与 DFT 证据', state: 'geometry' },
    ],
  },
  {
    name: '量子问题',
    steps: [
      { id: 'stage-quantum-model', number: '05', title: '量子区与活性空间', state: 'quantum_model' },
      { id: 'stage-circuit', number: '06', title: 'Hamiltonian 与线路', state: 'circuit' },
    ],
  },
  {
    name: '芯片执行',
    steps: [
      { id: 'stage-grouping', number: '07', title: '线路分组', state: 'grouping' },
      { id: 'stage-chip-mapping', number: '08', title: '芯片映射', state: 'chip_mapping' },
      { id: 'stage-routing', number: '09', title: '芯片路由', state: 'routing', unavailable: true },
      { id: 'stage-simulation', number: '10', title: '模拟执行', state: 'simulation', unavailable: true },
    ],
  },
  {
    name: '结果',
    steps: [
      { id: 'stage-evidence', number: '11', title: '结果与证据', state: 'evidence' },
    ],
  },
]

const StageHeading = defineComponent({
  props: { number: { type: String, required: true }, title: { type: String, required: true }, status: { type: String, required: true } },
  setup(props) {
    return () => h('div', { class: 'stage-heading' }, [h('span', props.number), h('div', [h('h3', props.title), h('p', props.status)])])
  },
})

const ValidationNotes = defineComponent({
  props: { validation: { type: Object, default: () => ({}) } },
  setup(props) {
    return () => h('div', { class: 'validation-notes' }, [
      ...(props.validation.errors || []).map(item => h('p', { class: 'error' }, `错误：${item}`)),
      ...(props.validation.warnings || []).map(item => h('p', { class: 'warning' }, `警告：${item}`)),
      ...(props.validation.suggestions || []).map(item => h('p', { class: 'suggestion' }, `建议：${item}`)),
    ])
  },
})

const ResultNotice = defineComponent({
  props: { title: { type: String, required: true }, status: { type: String, default: '' }, notes: { type: Array, default: () => [] } },
  setup(props) {
    return () => h('div', { class: 'result-notice' }, [h('div', [h('strong', props.title), h('span', props.status)]), ...props.notes.map(note => h('p', note))])
  },
})

const CapabilityBoundary = defineComponent({
  props: {
    title: { type: String, required: true },
    description: { type: String, required: true },
  },
  setup(props) {
    return () => h('div', { class: 'capability-boundary' }, [
      h('span', '能力边界'),
      h('div', [h('strong', props.title), h('p', props.description)]),
    ])
  },
})

const shortWorkflowId = computed(() => structureState.workflowId ? `分析记录 ${structureState.workflowId.slice(0, 12)}` : '尚未创建分析记录')
const shortHash = computed(() => structureState.sourceFileRecord?.file_hash?.slice(0, 16) || '--')
const identityLabel = computed(() => username.value || '当前研究用户')
const canConfirmSite = computed(() => {
  if (!isStructureValid.value) return false
  return siteForm.mode === 'suggested' ? Boolean(siteForm.selectedSiteId) : Boolean(siteForm.siteLabel && siteForm.centerIndices)
})
const hasElectronicReview = computed(() => structureState.electronicCandidates.some(item => item.quality_status === 'needs_model_review' || !item.converged))
const missingDftFields = computed(() => {
  const fields = [
    [structureState.optimizedStructure?.structure_id, '优化后结构'], [dftForm.software, '计算软件'],
    [dftForm.softwareVersion, '软件版本'], [dftForm.functional, '交换关联泛函'],
    [dftForm.basis, '基组或赝势'], [dftForm.dispersion, '色散修正'],
    [dftForm.initialMagneticMoments, '初始磁矩说明'], [dftForm.convergence, '收敛说明'],
    [dftForm.totalEnergy, '总能量'],
  ]
  return fields.filter(([value]) => value === '' || value === null || value === undefined).map(([, label]) => label)
})
const executionBackendLabel = computed(() => {
  const type = structureState.quantumResult?.execution?.execution_backend_type
  if (!type) return '未执行'
  return type === 'simulator' ? 'Simulator 模拟器' : type
})
const distributedPlan = computed(() => structureState.quantumResult?.execution?.distributed_execution || null)
const groupingCapabilityLabel = computed(() => {
  if (!distributedPlan.value) return '尚未分组'
  if (distributedPlan.value.capability_level === 'partition_planning_validation') return '规划验证已完成'
  if (distributedPlan.value.capability_level === 'no_partition_required') return '无需分组'
  return '分组不可用'
})
const dftEvidenceLabel = computed(() => structureState.dftImport?.status === 'dft_optimized' ? '完整且可审计' : structureState.dftImport ? '计算信息不完整' : '未导入')
const evidenceStrength = computed(() => {
  if (structureState.quantumResult && structureState.dftImport?.status === 'dft_optimized') return '结构 + DFT + 量子计算证据'
  if (structureState.quantumResult) return '结构驱动量子计算证据'
  if (structureState.geometryOptimization) return '几何建模证据'
  if (structureState.structure) return '结构解析证据'
  return '尚无证据'
})
const resultScope = computed(() => {
  if (structureState.quantumResult && structureState.dftImport?.status === 'dft_optimized') return '可作为科研候选依据，仍需同口径基准和实验验证'
  if (structureState.quantumResult) return '模拟器原型验证，不可直接用于最终推荐'
  return '仅用于继续建模，不可用于最终筛选'
})
const nextStepAdvice = computed(() => structureState.quantumResult
  ? '当前能量对应已记录的活性空间与执行后端，不等同于吸附能。最终推荐仍需同口径 DFT 对照、误差分析与实验验证。'
  : '继续补齐活性位点、优化几何、电荷自旋和活性空间，只有后端生成真实 Hamiltonian 与执行记录后才会形成量子计算证据。')
const artifactItems = computed(() => {
  const electronic = structureState.confirmedElectronicCandidate || {}
  const result = structureState.quantumResult || {}
  return [
    { type: '结构文件', id: structureState.sourceFileRecord?.file_id },
    { type: '几何结构', id: structureState.geometryOptimization?.geometry_artifact_id },
    { type: 'DFT 来源', id: structureState.dftImport?.source_artifact_id },
    { type: 'SCF 日志', id: electronic.log_artifact_id },
    { type: 'SCF 结果', id: electronic.result_artifact_id },
    { type: 'Hamiltonian Hash', id: result.fermionic?.artifact_hash },
    { type: 'Pauli Terms', id: result.qubit?.pauli_artifact_id },
    { type: 'QASM', id: result.circuit?.qasm_artifact_id },
    { type: '测量计划', id: result.circuit?.measurement_plan_artifact_id },
    { type: 'VQE 迭代记录', id: result.execution?.iteration_artifact_id },
  ].filter(item => item.id)
})

function isBusy(action) { return structureState.busyAction === action }
function stageState(step) {
  const states = {
    structure: structureState.structure ? 'complete' : 'active',
    site: structureState.confirmedActiveSite ? 'complete' : (structureState.structure ? 'active' : 'pending'),
    adsorption: selectedAdsorptionModel.value ? 'complete' : (structureState.confirmedActiveSite ? 'active' : 'pending'),
    geometry: structureState.geometryOptimization || structureState.dftImport ? 'complete' : (selectedAdsorptionModel.value ? 'active' : 'pending'),
    quantum_model: structureState.confirmedActiveSpace ? 'complete' : (canBuildQuantumRegion.value ? 'active' : 'pending'),
    circuit: structureState.quantumResult ? 'complete' : (canRunVqe.value ? 'active' : 'pending'),
    grouping: distributedPlan.value ? 'complete' : (structureState.quantumResult ? 'active' : 'pending'),
    chip_mapping: distributedPlan.value ? 'active' : 'pending',
    routing: 'unavailable',
    simulation: 'unavailable',
    evidence: structureState.quantumResult ? 'available' : 'pending',
  }
  return states[step.state] || 'pending'
}
function stepClass(step) {
  const state = stageState(step)
  return { active: state === 'active', complete: state === 'complete', unavailable: state === 'unavailable', available: state === 'available' }
}
function stepStatus(step) {
  const labels = { active: '当前步骤', complete: '已完成', pending: '待前置步骤', unavailable: '能力待接入', available: '可查看' }
  return labels[stageState(step)]
}
function scrollToStage(stageId) {
  document.getElementById(stageId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function handleSourceFileChange(file) { sourceUploadFile.value = file.raw }
function handleSourceFileRemove() { sourceUploadFile.value = null }
function handleOptimizedFileChange(file) { optimizedUploadFile.value = file.raw }
function handleOptimizedFileRemove() { optimizedUploadFile.value = null }

async function handleUploadSource() {
  await executeAction(() => uploadSourceStructure({ file: sourceUploadFile.value, ...sourceForm }), '结构已上传并完成解析')
}
async function handleUploadOptimized() {
  await executeAction(() => uploadOptimizedStructure({ file: optimizedUploadFile.value, materialName: optimizedForm.materialName, materialFamily: sourceForm.materialFamily, description: '外部优化几何' }), '优化后结构已解析')
}
async function handleSuggestSites() { await executeAction(requestActiveSiteSuggestions, '已生成活性位点建议') }
function selectSuggestedSite(site) {
  siteForm.selectedSiteId = site.active_site_id; siteForm.siteLabel = site.site_label
  siteForm.centerIndices = site.center_atom_indices.join(','); siteForm.neighborIndices = site.neighbor_atom_indices.join(',')
}
async function handleConfirmSite() {
  const payload = { site_source: siteForm.mode, site_id: siteForm.mode === 'suggested' ? siteForm.selectedSiteId : null, center_atom_indices: parseIntegerList(siteForm.centerIndices), neighbor_atom_indices: parseIntegerList(siteForm.neighborIndices), site_label: siteForm.siteLabel, user_note: siteForm.userNote || null }
  await executeAction(() => confirmActiveSite(payload), '活性位点已确认')
}
async function handleGenerateAdsorption() {
  await executeAction(() => createAdsorptionConformations({ polysulfide_species: adsorptionForm.species, max_conformations_per_species: adsorptionForm.count, initial_distance_angstrom: adsorptionForm.distance }), '吸附初始构型已生成')
}
async function handlePrepareGeometry() { await executeAction(prepareGeometry, '几何整理已完成') }
async function handleImportDft() { await executeAction(() => importDftEvidence(buildDftPayload()), 'DFT 导入信息已保存') }
async function handleBuildRegion() { await executeAction(() => buildQuantumRegion(regionForm), '量子区已建立') }
async function handleCalculateElectronic() {
  const payload = { charge_candidates: parseIntegerList(electronicForm.chargeCandidates), spin_strategy: 'explicit', spin_multiplicities: parseIntegerList(electronicForm.spinMultiplicities), requested_methods: ['UHF', 'ROHF'], basis_set: electronicForm.basisSet, max_scf_attempts: 3, spin_contamination_threshold: 0.5 }
  await executeAction(() => calculateElectronicCandidates(payload), '电荷与自旋候选计算完成')
}
async function handleConfirmElectronic(candidateId) { await executeAction(() => confirmElectronicCandidate(candidateId, '由前端科研输入确认工作台确认'), '电荷与自旋候选已确认') }
async function handleCalculateActiveSpaces() { await executeAction(calculateActiveSpaces, '活性空间候选已生成') }
async function handleConfirmActiveSpace(activeSpaceId) { await executeAction(() => confirmActiveSpaceCandidate(activeSpaceId), '活性空间已确认') }
async function handleRunQuantum() { await executeAction(() => executeQuantumCalculation(quantumForm), '量子线路与基准求解结果已生成') }
async function handleRefresh() { await executeAction(refreshWorkflow, '分析状态已刷新') }
async function handleReset() {
  try { await ElMessageBox.confirm('将清除当前浏览器中保存的分析进度，是否继续？', '开始新的分析', { type: 'warning' }); resetWorkflow(); sourceUploadFile.value = null; optimizedUploadFile.value = null; ElMessage.success('已准备新的化学分析') } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error.message || '重置失败') }
}
async function executeAction(action, successMessage) {
  try { await action(); ElMessage.success(successMessage) } catch (error) { ElMessage.error(structureState.lastError || error.message || '操作失败') }
}
function buildDftPayload() {
  const metadata = compactObject({ software: dftForm.software, software_version: dftForm.softwareVersion, calculation_type: 'geometry_optimization', functional: dftForm.functional, basis_or_pseudopotential: dftForm.basis, dispersion: dftForm.dispersion, spin_polarization: dftForm.spinPolarization, initial_magnetic_moments: dftForm.initialMagneticMoments, total_charge: dftForm.totalCharge, spin_multiplicity: dftForm.spinMultiplicity, convergence: dftForm.convergence ? { criterion: dftForm.convergence } : null, total_energy: dftForm.totalEnergy, energy_unit: 'Hartree', calculation_log_reference: dftForm.logReference, doi: dftForm.doi })
  return { optimized_structure_id: missingDftFields.value.length ? null : structureState.optimizedStructure?.structure_id || null, calculation_metadata: metadata, energy_bundle: buildEnergyBundle() }
}
function buildEnergyBundle() {
  if ([dftForm.adsorbedEnergy, dftForm.hostEnergy, dftForm.adsorbateEnergy].some(value => value === null || value === undefined)) return {}
  const signature = { software: dftForm.software, functional: dftForm.functional, basis: dftForm.basis, dispersion: dftForm.dispersion, spin: dftForm.spinPolarization ? 'polarized' : 'unpolarized' }
  return { adsorbed_system: { energy_hartree: dftForm.adsorbedEnergy, calculation_signature: signature }, host: { energy_hartree: dftForm.hostEnergy, calculation_signature: signature }, adsorbate: { energy_hartree: dftForm.adsorbateEnergy, calculation_signature: signature } }
}
function compactObject(value) { return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== '' && item !== null && item !== undefined)) }
function parseIntegerList(value) { return String(value || '').split(',').map(item => Number.parseInt(item.trim(), 10)).filter(Number.isInteger) }
function formatIndices(value) { return Array.isArray(value) && value.length ? value.join(', ') : '--' }
function formatNumber(value, digits = 2) { if (value === null || value === undefined || value === '') return '--'; const number = Number(value); return Number.isNaN(number) ? String(value) : number.toFixed(digits) }
function formatTime(value) { if (!value) return '--'; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false }) }
function formatLattice(value) { if (!value) return '分子/非周期结构'; if (Array.isArray(value)) return `${value.length} × ${value[0]?.length || 0} 晶格矩阵`; return '已记录晶胞参数' }
function activeSiteReason(site) { return site.site_type === 'transition_metal_center' ? '过渡金属中心及其第一配位壳层是优先吸附与电子结构复核区域。' : '基于局部元素环境和配位关系生成的候选位点。' }
function electronicCandidateSource(candidate) { return candidate.benchmark_case_id ? '基准/导入候选' : '后端 SCF 候选' }
function orbitalContributionLabel(space) { const details = space.orbital_metadata?.orbital_details; if (!Array.isArray(details) || !details.length) return '后端未返回原子轨道贡献'; return details.slice(0, 3).map(item => item.label || item.orbital_label || `轨道 ${item.orbital_index ?? '--'}`).join('、') }
function activeSpaceRiskLabel(space) { if (space.status === 'needs_model_review' || space.orbital_metadata?.spin_contamination_warning) return '自旋污染或模型边界需复核'; if (space.active_orbitals * 2 > 16) return '量子比特资源需求较高'; return '当前资源规模可进入验证' }
function statusLabel(status) { const map = { idle: '未开始', active_site_pending: '待确认活性位点', active_site_confirmed: '活性位点已确认', adsorption_models_generated: '初始构型已生成', geometry_optimized: '几何已准备', quantum_region_built: '量子区已建立', eligible_for_confirmation: '可确认', needs_model_review: '需要补充科研建模信息', active_space_pending: '待确认活性空间', active_space_confirmed: '活性空间已确认', validation_failed: '结构校验失败', metadata_incomplete: '计算信息不完整', completed: '已完成', failed: '失败', partial_result: '部分完成', suggested: '待确认', confirmed: '已确认' }; return map[status] || status || '未开始' }
function statusType(status) { if (['completed', 'confirmed', 'eligible_for_confirmation', 'active_space_confirmed', 'quantum_region_built'].includes(status)) return 'success'; if (['failed', 'validation_failed'].includes(status)) return 'danger'; if (['needs_model_review', 'metadata_incomplete', 'partial_result'].includes(status)) return 'warning'; return 'info' }
</script>

<style scoped>
.structure-workbench { color: #101828; }
.workbench-head, .stage-panel, .step-rail { border: 1px solid rgba(166, 204, 247, .14); border-radius: 8px; box-shadow: 0 18px 40px rgba(2, 10, 18, .14); }
.workbench-head { min-height: 150px; padding: 24px; display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; color: #eef7ff; background: linear-gradient(110deg, rgba(4, 14, 27, .98), rgba(8, 44, 58, .92)); }
.eyebrow { color: #63d8d0; font-size: .72rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.workbench-head h2 { margin: 8px 0 0; font-size: 1.55rem; }.workbench-head p { margin: 8px 0 0; color: #a9bed0; }
.head-actions, .toolbar-line, .action-row, .input-strip, .region-form, .quantum-config { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.global-alert { margin-top: 16px; }.workbench-layout { min-width: 0; margin-top: 18px; display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 18px; align-items: start; }
.benchmark-guide { margin-top: 16px; padding: 14px 18px; border: 1px solid rgba(91, 224, 210, .18); border-radius: 8px; display: grid; grid-template-columns: minmax(220px, .6fr) minmax(0, 1.4fr) auto; align-items: center; gap: 18px; color: #dcebf6; background: linear-gradient(100deg, rgba(10, 35, 49, .96), rgba(9, 25, 41, .96)); }.benchmark-guide div { display: grid; gap: 5px; }.benchmark-guide span { color: #5be0d2; font-size: .7rem; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }.benchmark-guide p { margin: 0; color: #9fb4c6; font-size: .78rem; line-height: 1.65; }
.step-rail { position: sticky; top: 18px; max-height: calc(100vh - 36px); padding: 16px; overflow-y: auto; background: rgba(248, 251, 255, .97); }
.source-badge { padding: 12px; border-radius: 6px; background: #0c2131; color: #eef7ff; display: grid; gap: 5px; }.source-badge span, .source-badge small { color: #8fa7bb; font-size: .72rem; }
.stage-group { margin-top: 16px; }.stage-group h3 { margin: 0 0 6px; color: #98a2b3; font-size: .68rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }.step-rail ol { margin: 0; padding: 0; list-style: none; display: grid; }.step-rail li { min-height: 58px; border-left: 2px solid #dbe4ed; color: #667085; }.step-rail li button { width: 100%; min-height: 58px; padding: 8px 6px; border: 0; display: grid; grid-template-columns: 32px minmax(0, 1fr); align-items: center; gap: 8px; color: inherit; text-align: left; background: transparent; cursor: pointer; }.step-rail li button > span:first-child { font-family: Consolas, monospace; font-size: .72rem; }.step-rail li button > span:last-child { min-width: 0; display: grid; gap: 4px; }.step-rail li strong { font-size: .8rem; }.step-rail li small { font-size: .68rem; }.step-rail li:hover { background: #f2f6fa; }.step-rail li.active { border-color: #1677ff; color: #2456b8; background: #edf5ff; }.step-rail li.complete { border-color: #18aa8d; color: #137a68; }.step-rail li.unavailable { border-color: #e3a008; color: #8a5a00; background: #fff9eb; }.step-rail li.available { border-color: #7b61c9; color: #6146ad; }
.stage-stack { min-width: 0; display: grid; gap: 18px; }.stage-panel { min-width: 0; padding: 20px; scroll-margin-top: 18px; background: rgba(248, 251, 255, .98); }.stage-panel.locked { opacity: .68; }
.stage-heading { margin-bottom: 18px; display: grid; grid-template-columns: 42px 1fr; align-items: center; gap: 10px; }.stage-heading > span { width: 38px; height: 38px; border-radius: 6px; display: grid; place-items: center; background: #0d2738; color: #5be0d2; font: 700 .75rem Consolas, monospace; }.stage-heading h3 { margin: 0; font-size: 1.08rem; }.stage-heading p { margin: 5px 0 0; color: #667085; font-size: .8rem; }
.two-column, .dft-layout { display: grid; grid-template-columns: minmax(300px, .8fr) minmax(0, 1.2fr); gap: 18px; }.research-form, .dft-form { display: grid; gap: 10px; }.research-form :deep(.el-form-item) { margin-bottom: 2px; }
.upload-copy { min-height: 82px; display: grid; place-content: center; gap: 7px; }.upload-copy span { color: #667085; font-size: .78rem; }.evidence-box, .branch-panel, .result-notice, .candidate-control, .scope-box { padding: 16px; border: 1px solid #dfe7ef; border-radius: 6px; background: #fff; }
.box-title, .branch-panel, .result-notice > div { display: flex; justify-content: space-between; gap: 12px; align-items: center; }.metadata-grid { margin: 16px 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.metadata-grid div, .active-space-card dl div { display: grid; gap: 4px; }.metadata-grid dt, .active-space-card dt { color: #667085; font-size: .72rem; }.metadata-grid dd, .active-space-card dd { margin: 0; font-size: .86rem; font-weight: 700; }
.validation-notes { display: grid; gap: 6px; }.validation-notes p { margin: 0; padding: 8px; border-radius: 4px; font-size: .78rem; }.validation-notes .error { background: #fff0ee; color: #a52a1f; }.validation-notes .warning { background: #fff7e6; color: #875000; }.validation-notes .suggestion { background: #eef7ff; color: #2456b8; }.empty-copy, .empty-evidence { min-height: 130px; display: grid; place-content: center; text-align: center; color: #667085; }.empty-copy p, .empty-evidence p { margin: 7px 0 0; max-width: 580px; }
.choice-grid, .model-grid, .active-space-grid, .quantum-results, .concept-grid { margin: 14px 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }.choice-card, .model-card { padding: 14px; border: 1px solid #dfe7ef; border-radius: 6px; display: grid; gap: 7px; background: #fff; color: #101828; text-align: left; cursor: pointer; }.choice-card.selected, .model-card.selected { border-color: #1677ff; box-shadow: inset 3px 0 #1677ff; background: #f1f7ff; }.choice-card span, .choice-card small, .model-card small { color: #667085; font-size: .72rem; }.manual-site-form { margin-top: 14px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }.action-row { margin-top: 14px; }.confirmed-note { color: #137a68; font-size: .82rem; font-weight: 700; }
.input-strip { margin-bottom: 14px; }.input-strip label, .region-form label, .quantum-config label { display: inline-flex; align-items: center; gap: 8px; color: #475467; font-size: .78rem; }.model-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }.branch-panel { margin-top: 14px; }.branch-panel p { margin: 6px 0 0; color: #667085; font-size: .8rem; }.dft-layout { margin-top: 16px; }.dft-form { grid-template-columns: repeat(2, minmax(0, 1fr)); }.dft-form :deep(.el-form-item) { margin: 0; }.inline-fields, .energy-fields { width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }.energy-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }.result-notice { margin-top: 14px; border-left: 3px solid #18aa8d; }.result-notice span { color: #667085; font-family: Consolas, monospace; font-size: .74rem; }.result-notice p { margin: 8px 0 0; color: #667085; font-size: .78rem; }
.concept-grid > div { padding: 14px; border-top: 2px solid #1f8eea; background: #eef6fc; }.concept-grid p { margin: 7px 0 0; color: #667085; font-size: .78rem; line-height: 1.55; }.region-form { margin: 14px 0; padding: 14px; background: #fff; }.candidate-control { margin-top: 14px; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: 14px; }.candidate-control form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }.candidate-control :deep(.el-form-item) { margin: 0; }
.table-scroll { width: 100%; min-width: 0; max-width: 100%; margin-top: 14px; overflow-x: auto; }.research-table { width: 100%; min-width: 920px; border-collapse: collapse; background: #fff; }.research-table th, .research-table td { padding: 11px 10px; border-bottom: 1px solid #e5eaf0; text-align: left; font-size: .76rem; }.research-table th { color: #667085; background: #f3f6f9; }.empty-cell { text-align: center !important; color: #98a2b3; }.active-space-card, .quantum-results article { padding: 14px; border: 1px solid #dfe7ef; border-radius: 6px; background: #fff; }.active-space-card > div, .quantum-results article { display: grid; gap: 6px; }.active-space-card span, .quantum-results span, .scope-box span { color: #667085; font-size: .72rem; }.active-space-card dl { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }.active-space-card p { min-height: 42px; color: #667085; font-size: .76rem; line-height: 1.5; }
.quantum-config { padding: 14px; background: #0b1c2a; border-radius: 6px; }.quantum-config label, .quantum-config :deep(.el-checkbox__label) { color: #dbe9f5; }.quantum-results { grid-template-columns: repeat(4, minmax(0, 1fr)); }.quantum-results article { border-top: 2px solid #18aa8d; }.quantum-results small { color: #667085; }.evidence-timeline { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }.evidence-timeline div { min-height: 76px; padding: 12px; border-top: 3px solid #cfd8e3; background: #fff; display: grid; gap: 7px; }.evidence-timeline div.complete { border-color: #18aa8d; }.evidence-timeline span { color: #667085; font-size: .72rem; }.scope-box { margin-top: 14px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.scope-box div { display: grid; gap: 6px; }.scope-box p { grid-column: 1 / -1; margin: 0; padding-top: 12px; border-top: 1px solid #e5eaf0; color: #475467; line-height: 1.65; }
.execution-summary-grid, .subcircuit-list { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }.execution-summary-grid article, .subcircuit-list article { padding: 14px; border: 1px solid #dfe7ef; border-radius: 6px; display: grid; gap: 7px; background: #fff; }.execution-summary-grid article { border-top: 2px solid #18aa8d; }.execution-summary-grid span, .execution-summary-grid small, .subcircuit-list span, .subcircuit-list small { color: #667085; font-size: .72rem; }.subcircuit-list { margin-top: 14px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.capability-pending { border-style: dashed; }.capability-form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)) auto; align-items: end; gap: 12px; }.capability-form-grid label { min-width: 0; display: grid; gap: 7px; color: #475467; font-size: .76rem; font-weight: 700; }.expected-output-grid { margin-top: 14px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }.expected-output-grid span { min-height: 58px; padding: 10px; border: 1px dashed #cfd8e3; border-radius: 6px; display: grid; place-items: center; color: #667085; background: #f7f9fb; font-size: .74rem; text-align: center; }.capability-boundary { margin-top: 16px; padding: 14px; border: 1px solid #f0d28b; border-radius: 6px; display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 12px; background: #fff9eb; }.capability-boundary > span { padding: 4px 7px; border-radius: 999px; color: #8a5a00; background: #f8df9d; font-size: .68rem; font-weight: 800; }.capability-boundary div { display: grid; gap: 5px; }.capability-boundary p { margin: 0; color: #775a22; font-size: .78rem; line-height: 1.6; }
.dft-form > .el-alert, .dft-form > .el-button { grid-column: 1 / -1; }
.molecule-mini { width: 100%; height: 54px; position: relative; display: block; border-radius: 4px; overflow: hidden; background: linear-gradient(180deg, #071827, #0d2a38); }.molecule-mini::before { content: ''; position: absolute; left: 17%; right: 17%; top: 26px; height: 1px; background: linear-gradient(90deg, #d8a942, #62d9e1, #d8a942); transform: rotate(-7deg); }.molecule-mini i { width: 11px; height: 11px; position: absolute; top: 20px; border: 1px solid rgba(255,255,255,.5); border-radius: 50%; background: radial-gradient(circle at 30% 25%, rgba(255,255,255,.9), rgba(224,178,71,.72) 35%, rgba(224,178,71,.18)); box-shadow: 0 0 12px rgba(224,178,71,.45); }.molecule-mini i:nth-child(1) { left: 15%; }.molecule-mini i:nth-child(2) { left: 32%; top: 15px; }.molecule-mini i:nth-child(3) { left: 49%; top: 23px; }.molecule-mini i:nth-child(4) { left: 66%; top: 17px; }.molecule-mini i:nth-child(5) { left: 82%; top: 24px; }
.active-space-card > small { display: block; margin-top: 6px; color: #667085; font-size: .7rem; line-height: 1.45; }
.quantum-detail-grid { margin: 14px 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.quantum-detail-grid dl { margin: 0; padding: 14px; border: 1px solid #dfe7ef; border-radius: 6px; background: #fff; display: grid; gap: 10px; }.quantum-detail-grid dl div { display: grid; gap: 4px; }.quantum-detail-grid dt { color: #667085; font-size: .7rem; }.quantum-detail-grid dd { margin: 0; overflow-wrap: anywhere; font-size: .78rem; font-weight: 700; }
.artifact-list { margin-top: 14px; padding: 14px; border: 1px solid #dfe7ef; border-radius: 6px; display: grid; gap: 8px; background: #fff; }.artifact-list > span { padding: 8px 0; border-bottom: 1px solid #eef1f5; display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 10px; }.artifact-list i { color: #667085; font-size: .72rem; font-style: normal; }.artifact-list b { overflow-wrap: anywhere; font-size: .74rem; }
.mono { font-family: Consolas, 'SFMono-Regular', monospace; }.empty-inline { color: #667085; font-size: .8rem; }
@media (max-width: 1180px) { .workbench-layout { grid-template-columns: 220px minmax(0, 1fr); }.two-column, .dft-layout { grid-template-columns: 1fr; }.model-grid, .quantum-results, .execution-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.capability-form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 820px) { .workbench-head { align-items: flex-start; flex-direction: column; }.workbench-layout { grid-template-columns: 1fr; }.step-rail { position: static; max-height: none; }.stage-group ol { grid-template-columns: repeat(2, 1fr); }.choice-grid, .concept-grid, .active-space-grid, .dft-form, .candidate-control form { grid-template-columns: 1fr; }.candidate-control { grid-template-columns: 1fr; }.evidence-timeline, .expected-output-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .model-grid, .quantum-results, .metadata-grid, .scope-box, .manual-site-form, .execution-summary-grid, .subcircuit-list, .capability-form-grid, .expected-output-grid { grid-template-columns: 1fr; }.energy-fields, .inline-fields { grid-template-columns: 1fr; } }
@media (max-width: 1180px) { .benchmark-guide { grid-template-columns: 1fr auto; }.benchmark-guide p { grid-column: 1 / -1; } }
@media (max-width: 560px) { .quantum-detail-grid, .benchmark-guide { grid-template-columns: 1fr; } }
</style>

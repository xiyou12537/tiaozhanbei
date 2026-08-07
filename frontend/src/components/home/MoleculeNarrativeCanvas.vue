<template>
  <section
    id="process"
    ref="sectionRef"
    class="narrative"
    :class="{ 'is-reduced-motion': reducedMotion, 'is-fallback': fallback }"
    aria-label="(LiH)₄ 团簇到能量一致性验证的连续过程"
    data-testid="molecule-narrative-canvas"
  >
    <div class="narrative-pin" :data-active-stage="activeStage">
      <canvas ref="canvasRef" class="narrative-canvas" aria-hidden="true"></canvas>
      <div class="scene-fallback" aria-hidden="true">
        <div class="fallback-atoms">
          <i v-for="atom in fallbackAtoms" :key="atom.id" :class="['fallback-atom', atom.element.toLowerCase()]" :style="{ left: `${atom.x}%`, top: `${atom.y}%` }">{{ atom.element }}</i>
          <span v-for="edge in fallbackEdges" :key="edge.id" class="fallback-edge" :style="edge.style"></span>
        </div>
      </div>

      <section v-show="activeStage === 1" class="semantic-scene quantum-circuit-diagram" data-testid="quantum-circuit-diagram" aria-label="量子线路结构">
        <p class="diagram-kicker">LOGICAL CIRCUIT / QASM</p>
        <div class="circuit-body">
          <div class="circuit-row"><span class="qubit-label">q0</span><div class="circuit-wire"><b class="gate gate-x">X</b><b class="gate gate-ry">RY(θ)</b></div></div>
          <div class="circuit-row"><span class="qubit-label">q1</span><div class="circuit-wire"><b class="gate gate-ry gate-ry-middle">RY(θ)</b></div></div>
          <div class="circuit-row"><span class="qubit-label">q2…</span><div class="circuit-wire"><b class="gate gate-ry gate-ry-lower">RY(θ)</b></div></div>
          <span class="cx-link cx-link-one" aria-label="CX，从 q0 到 q1"><i class="cx-control">●</i><b></b><i class="cx-target">⊕</i></span>
          <span class="cx-link cx-link-two" aria-label="CX，从 q1 到 q2"><i class="cx-control">●</i><b></b><i class="cx-target">⊕</i></span>
        </div>
        <p class="diagram-placeholder" v-if="circuitEvidence.qasm == null">等待真实 Workflow / QASM</p>
      </section>

      <section v-show="activeStage === 2" class="semantic-scene virtual-qpu-diagram" data-testid="virtual-qpu-diagram" aria-label="三颗虚拟量子芯片的分布式线路">
        <p class="diagram-kicker">DISTRIBUTED EXECUTION</p>
        <div class="qpu-cluster">
          <article v-for="chip in virtualQpus" :key="chip.id" class="virtual-chip">
            <header>{{ chip.label }}</header>
            <div class="chip-board">
              <div class="topology-frame" aria-label="physical coupling map">
                <span v-for="edge in chipTopologyEdges" :key="edge" class="physical-coupling" :class="edge"></span>
                <i v-for="node in chipTopologyNodes" :key="node.id" class="physical-node" :class="node.position">{{ node.id }}</i>
                <div v-if="chip.gate === 'CX'" class="chip-local-circuit chip-local-cx" aria-label="芯片内 CX 有效耦合边">
                  <b class="local-control">●</b><i></i><b class="local-target">⊕</b>
                </div>
                <div v-else class="chip-local-circuit"><b>{{ chip.gate }}</b></div>
                <span v-if="chip.hasSwap" class="chip-route" aria-label="芯片内路由 SWAP"><i>×</i><b>SWAP</b></span>
              </div>
            </div>
            <footer>{{ chip.hasSwap ? '芯片内路由 · SWAP' : '局部线路映射' }}</footer>
          </article>
          <div class="inter-chip-communication" aria-label="跨芯片通信"><i></i><b>跨芯片通信</b><small>· CX</small><i></i></div>
        </div>
        <p class="diagram-placeholder">等待真实 Workflow / 物理映射</p>
      </section>

      <section v-show="activeStage === 3" class="semantic-scene energy-consistency-instrument" data-testid="energy-consistency-instrument" aria-label="未分区与分布式能量一致性验证">
        <p class="diagram-kicker">ENERGY CONSISTENCY</p>
        <div class="energy-panel">
          <div class="energy-reading"><span>未分区 VQE 能量</span><i class="energy-channel baseline-a"></i><strong>— Ha</strong></div>
          <div class="energy-reading"><span>分布式模拟能量</span><i class="energy-channel baseline-b"></i><strong>— Ha</strong></div>
          <div class="energy-alignment"><i></i><b class="energy-check">✓</b><i></i><span>同一基准线</span></div>
          <div class="energy-reading error-reading"><span>绝对误差 |ΔE|</span><i class="energy-channel"></i><strong>— Ha</strong></div>
        </div>
        <p class="diagram-placeholder">等待真实 Workflow</p>
      </section>

      <div class="narrative-topline">
        <span class="scene-index">0{{ activeStage + 1 }} / 04</span>
        <span class="scene-name">(LiH)₄ · WORKFLOW ORIGIN</span>
      </div>

      <div class="narrative-copy">
        <p v-for="(stage, index) in stages" :key="stage.id" class="narrative-stage" :class="{ active: activeStage === index }" :aria-hidden="activeStage !== index" data-testid="narrative-stage">
          {{ stage.sentence }}
        </p>
      </div>

      <div class="narrative-metrics" aria-label="Workflow 结构化数据占位" aria-live="polite">
        <div v-for="metric in visibleMetrics" :key="metric.key" class="narrative-metric" data-testid="workflow-metric">
          <span>{{ metric.label }}</span>
          <strong>{{ formatMetric(metric.value) }}</strong>
          <small>{{ metric.value == null ? '等待真实 Workflow' : metric.unit }}</small>
        </div>
      </div>

      <p class="narrative-disclaimer">模拟器 · 虚拟节点逻辑分布式模拟 · 非真实 QPU</p>
      <span class="scroll-cue" aria-hidden="true">SCROLL TO FOLLOW <b>↓</b></span>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import * as THREE from 'three'

const sectionRef = ref(null)
const canvasRef = ref(null)
const activeStage = ref(0)
const fallback = ref(false)
const reducedMotion = ref(false)

const stages = [
  { id: 'molecule_structure', sentence: '从一组原子开始。' },
  { id: 'quantum_circuit', sentence: '化作一条量子线路。' },
  { id: 'chip_topology_routing', sentence: '在芯片之间展开。' },
  { id: 'energy_validation', sentence: '抵达同一个答案。' },
]

// Values remain null until a real (LiH)₄ Workflow fixture is available; the UI intentionally renders an em dash.
const workflowEvidence = Object.freeze({
  qubits: null,
  partitions: null,
  swapCount: null,
  communicationCount: null,
  unpartitionedEnergy: null,
  distributedEnergy: null,
  absoluteError: null,
})

// Gate shape and chip routing remain structural placeholders until a real (LiH)₄ Workflow/QASM is available.
const circuitEvidence = Object.freeze({ qasm: null, gates: null })
// A planar heavy-hex-inspired silhouette keeps physical coupling edges readable until the real map arrives.
const chipTopologyNodes = Object.freeze([
  { id: 'p0', position: 'node-top-a' }, { id: 'p1', position: 'node-top-b' }, { id: 'p2', position: 'node-top-c' },
  { id: 'p3', position: 'node-bottom-a' }, { id: 'p4', position: 'node-bottom-b' }, { id: 'p5', position: 'node-bottom-c' },
])
const chipTopologyEdges = Object.freeze([
  'coupling-top-a', 'coupling-top-b', 'coupling-bottom-a', 'coupling-bottom-b',
  'coupling-vertical', 'coupling-vertical-mid', 'coupling-vertical-end',
])
const virtualQpus = Object.freeze([
  { id: '01', label: 'VIRTUAL QPU 01', gate: 'X', hasSwap: false },
  { id: '02', label: 'VIRTUAL QPU 02', gate: 'RY(θ)', hasSwap: true },
  { id: '03', label: 'VIRTUAL QPU 03', gate: 'CX', hasSwap: false },
])

const metricSets = [
  [
    { key: 'qubits', label: '量子比特', value: workflowEvidence.qubits, unit: 'QUBITS' },
    { key: 'partitions', label: '虚拟节点', value: workflowEvidence.partitions, unit: 'PARTITIONS' },
  ],
  [
    { key: 'qubits', label: '量子比特', value: workflowEvidence.qubits, unit: 'QUBITS' },
    { key: 'swapCount', label: 'SWAP', value: workflowEvidence.swapCount, unit: 'ROUTING' },
  ],
  [
    { key: 'partitions', label: '虚拟节点', value: workflowEvidence.partitions, unit: 'PARTITIONS' },
    { key: 'swapCount', label: 'SWAP', value: workflowEvidence.swapCount, unit: 'ROUTING' },
    { key: 'communicationCount', label: '通信', value: workflowEvidence.communicationCount, unit: 'EVENTS' },
  ],
  [
    { key: 'unpartitionedEnergy', label: '原始能量', value: workflowEvidence.unpartitionedEnergy, unit: 'HARTREE' },
    { key: 'distributedEnergy', label: '分布式能量', value: workflowEvidence.distributedEnergy, unit: 'HARTREE' },
    { key: 'absoluteError', label: '绝对误差', value: workflowEvidence.absoluteError, unit: 'HARTREE' },
  ],
]
const visibleMetrics = computed(() => metricSets[activeStage.value].slice(0, 4))

const fallbackAtoms = [
  { id: 'li-1', element: 'Li', x: 40, y: 34 }, { id: 'li-2', element: 'Li', x: 61, y: 43 },
  { id: 'li-3', element: 'Li', x: 38, y: 65 }, { id: 'li-4', element: 'Li', x: 59, y: 73 },
  { id: 'h-1', element: 'H', x: 51, y: 28 }, { id: 'h-2', element: 'H', x: 67, y: 59 },
  { id: 'h-3', element: 'H', x: 29, y: 51 }, { id: 'h-4', element: 'H', x: 49, y: 80 },
]
const fallbackEdges = [
  { id: 'a', style: { left: '36%', top: '43%', width: '29%', transform: 'rotate(18deg)' } },
  { id: 'b', style: { left: '32%', top: '58%', width: '33%', transform: 'rotate(-20deg)' } },
  { id: 'c', style: { left: '42%', top: '35%', width: '20%', transform: 'rotate(56deg)' } },
]

let renderer
let scene
let camera
let animationFrame
let resizeObserver
let intersectionObserver
let mediaQuery
let scrollHandler
let started = false
let visible = true
let compactLayout = false
let cameraBaseZ = 8.6
let moleculeGroup
let circuitGroup
let qpuGroup
let energyGroup
let energyTracks = []

const color = {
  ink: 0x17201d,
  moss: 0x6f914f,
  lime: 0xb5f04c,
  silver: 0xb8c1ba,
  warm: 0xf6f7f1,
  line: 0x7d9183,
}

function formatMetric(value) {
  return value == null ? '—' : String(value)
}

function makeLine(points, material, dashed = false) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const line = dashed ? new THREE.Line(geometry, material) : new THREE.Line(geometry, material)
  line.userData.baseOpacity = material.opacity
  if (dashed) line.computeLineDistances()
  return line
}

function makeAtom(element, position) {
  const isLithium = element === 'Li'
  const material = new THREE.MeshStandardMaterial({
    color: isLithium ? color.silver : color.warm,
    roughness: isLithium ? 0.35 : 0.48,
    metalness: isLithium ? 0.28 : 0.04,
    transparent: true,
    opacity: 1,
  })
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(isLithium ? 0.42 : 0.22, 28, 18), material)
  mesh.position.copy(position)
  mesh.userData.element = element
  return mesh
}

function buildMoleculeGroup() {
  moleculeGroup = new THREE.Group()
  // Confirmed compact-cluster motif: alternating Li/H vertices of a cubane-like Li4H4 fragment, not four LiH dimers.
  const radius = 0.92
  const atoms = [
    { element: 'Li', position: new THREE.Vector3(-radius, -radius, -radius) },
    { element: 'Li', position: new THREE.Vector3(-radius, radius, radius) },
    { element: 'Li', position: new THREE.Vector3(radius, -radius, radius) },
    { element: 'Li', position: new THREE.Vector3(radius, radius, -radius) },
    { element: 'H', position: new THREE.Vector3(-radius, -radius, radius) },
    { element: 'H', position: new THREE.Vector3(-radius, radius, -radius) },
    { element: 'H', position: new THREE.Vector3(radius, -radius, -radius) },
    { element: 'H', position: new THREE.Vector3(radius, radius, radius) },
  ]
  atoms.forEach(atom => moleculeGroup.add(makeAtom(atom.element, atom.position)))
  const bondMaterial = new THREE.LineBasicMaterial({ color: color.moss, transparent: true, opacity: 0.5 })
  const electronMaterial = new THREE.LineBasicMaterial({ color: color.lime, transparent: true, opacity: 0.18 })
  for (let left = 0; left < atoms.length; left += 1) {
    for (let right = left + 1; right < atoms.length; right += 1) {
      const distance = atoms[left].position.distanceTo(atoms[right].position)
      if (atoms[left].element !== atoms[right].element && Math.abs(distance - radius * 2) < 0.01) {
        moleculeGroup.add(makeLine([atoms[left].position, atoms[right].position], bondMaterial))
      }
    }
  }
  moleculeGroup.add(makeLine([atoms[0].position, atoms[7].position], electronMaterial))
  moleculeGroup.add(makeLine([atoms[1].position, atoms[6].position], electronMaterial))
  moleculeGroup.position.set(compactLayout ? 0.55 : 1.7, 0.05, 0)
  scene.add(moleculeGroup)
}

function buildCircuitGroup() {
  circuitGroup = new THREE.Group()
  const wireMaterial = new THREE.LineBasicMaterial({ color: color.ink, transparent: true, opacity: 0.78 })
  const gateMaterial = new THREE.MeshStandardMaterial({ color: color.moss, roughness: 0.55, metalness: 0.12, transparent: true, opacity: 0.94 })
  for (let row = 0; row < 4; row += 1) {
    const y = 1.05 - row * 0.7
    circuitGroup.add(makeLine([new THREE.Vector3(-2.7, y, 0), new THREE.Vector3(2.7, y, 0)], wireMaterial))
    for (let column = 0; column < 4; column += 1) {
      const gate = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.36, 0.12), gateMaterial)
      gate.position.set(-1.9 + column * 1.22 + (row % 2) * 0.1, y, 0.08)
      circuitGroup.add(gate)
    }
  }
  const connectorMaterial = new THREE.LineBasicMaterial({ color: color.lime, transparent: true, opacity: 0.82 })
  circuitGroup.add(makeLine([new THREE.Vector3(-0.08, 1.05, 0.1), new THREE.Vector3(-0.08, -1.05, 0.1)], connectorMaterial))
  circuitGroup.add(makeLine([new THREE.Vector3(1.16, 0.35, 0.1), new THREE.Vector3(1.16, -0.35, 0.1)], connectorMaterial))
  circuitGroup.position.set(compactLayout ? 0.3 : 0.85, -0.05, 0)
  circuitGroup.scale.setScalar(compactLayout ? 0.74 : 1)
  scene.add(circuitGroup)
}

function addLocalCircuit(chip, width) {
  const localCircuit = new THREE.Group()
  const localWire = new THREE.LineBasicMaterial({ color: color.ink, transparent: true, opacity: 0.8 })
  const localGate = new THREE.MeshStandardMaterial({ color: color.moss, roughness: 0.5, metalness: 0.14, transparent: true, opacity: 0.96 })
  for (let row = 0; row < 3; row += 1) {
    const y = 0.43 - row * 0.43
    localCircuit.add(makeLine([new THREE.Vector3(-width / 2 + 0.22, y, 0.12), new THREE.Vector3(width / 2 - 0.22, y, 0.12)], localWire))
    const gate = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.24, 0.1), localGate)
    gate.position.set(row === 1 ? 0.22 : -0.18, y, 0.16)
    localCircuit.add(gate)
  }
  chip.add(localCircuit)
}

function buildQpuGroup() {
  qpuGroup = new THREE.Group()
  const width = 1.82
  const height = 1.52
  const placements = compactLayout
    ? [new THREE.Vector3(0.45, 2.15, 0), new THREE.Vector3(0.45, 0, 0), new THREE.Vector3(0.45, -2.15, 0)]
    : [new THREE.Vector3(-2.55, -0.35, 0), new THREE.Vector3(0, -0.35, 0), new THREE.Vector3(2.55, -0.35, 0)]
  const chips = placements.map((position, index) => {
    const chip = new THREE.Group()
    const frameMaterial = new THREE.LineBasicMaterial({ color: index === 1 ? color.moss : color.ink, transparent: true, opacity: 0.86 })
    const frame = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(width, height, 0.18)), frameMaterial)
    chip.add(frame)
    addLocalCircuit(chip, width)
    chip.position.copy(position)
    qpuGroup.add(chip)
    return chip
  })
  const interChip = new THREE.Group()
  const interMaterial = new THREE.LineDashedMaterial({ color: color.lime, transparent: true, opacity: 0.96, dashSize: 0.14, gapSize: 0.08 })
  if (compactLayout) {
    interChip.add(makeLine([new THREE.Vector3(0.45, 1.39, 0.18), new THREE.Vector3(0.45, 0.76, 0.18)], interMaterial, true))
    interChip.add(makeLine([new THREE.Vector3(0.45, -0.76, 0.18), new THREE.Vector3(0.45, -1.39, 0.18)], interMaterial, true))
  } else {
    interChip.add(makeLine([new THREE.Vector3(-1.64, -0.35, 0.18), new THREE.Vector3(-0.91, -0.35, 0.18)], interMaterial, true))
    interChip.add(makeLine([new THREE.Vector3(0.91, -0.35, 0.18), new THREE.Vector3(1.64, -0.35, 0.18)], interMaterial, true))
  }
  qpuGroup.add(interChip)
  qpuGroup.userData.chips = chips
  qpuGroup.userData.interChip = interChip
  qpuGroup.position.set(compactLayout ? 0 : 0.08, compactLayout ? -0.56 : -0.48, 0)
  qpuGroup.scale.setScalar(compactLayout ? 0.64 : 1)
  scene.add(qpuGroup)
}

function createEnergyTrack(trackColor, startY) {
  const count = 80
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3))
  const material = new THREE.LineBasicMaterial({ color: trackColor, transparent: true, opacity: 0.92 })
  const line = new THREE.Line(geometry, material)
  line.userData = { baseOpacity: material.opacity, startY, endY: 0, count }
  energyTracks.push(line)
  return line
}

function buildEnergyGroup() {
  energyGroup = new THREE.Group()
  energyTracks = [
    createEnergyTrack(color.ink, 0.96),
    createEnergyTrack(color.lime, -0.88),
  ]
  energyTracks.forEach(track => energyGroup.add(track))
  const merge = new THREE.Mesh(new THREE.SphereGeometry(0.14, 18, 12), new THREE.MeshStandardMaterial({ color: color.lime, roughness: 0.35, metalness: 0.16, transparent: true, opacity: 0.95 }))
  merge.position.set(2.8, 0, 0.08)
  energyGroup.add(merge)
  energyGroup.position.set(compactLayout ? 0.18 : 1.14, -0.05, 0)
  energyGroup.scale.setScalar(compactLayout ? 0.72 : 0.86)
  scene.add(energyGroup)
}

function buildScene() {
  compactLayout = window.innerWidth <= 620
  scene = new THREE.Scene()
  scene.fog = new THREE.Fog(color.warm, 8, 18)
  camera = new THREE.PerspectiveCamera(compactLayout ? 38 : 32, 1, 0.1, 100)
  cameraBaseZ = compactLayout ? 13.4 : 8.6
  camera.position.set(0, 0.15, cameraBaseZ)
  scene.add(new THREE.AmbientLight(0xf5f7f0, 2.3))
  const keyLight = new THREE.DirectionalLight(0xd7e8c7, 3.6)
  keyLight.position.set(-3, 5, 7)
  scene.add(keyLight)
  const rimLight = new THREE.PointLight(color.lime, 2.2, 9)
  rimLight.position.set(3, -2, 4)
  scene.add(rimLight)
  buildMoleculeGroup()
  buildCircuitGroup()
  buildQpuGroup()
  buildEnergyGroup()
}

function setGroupOpacity(group, opacity) {
  if (!group) return
  group.traverse(object => {
    if (!object.material) return
    object.material.transparent = true
    object.material.opacity = opacity * (object.userData.baseOpacity ?? 1)
  })
}

function updateEnergyTracks(amount) {
  energyTracks.forEach(track => {
    const positions = track.geometry.attributes.position
    const { count, startY, endY } = track.userData
    for (let index = 0; index < count; index += 1) {
      const t = index / (count - 1)
      const x = -2.9 + t * 5.7
      const y = startY * (1 - t) * (1 - amount * 0.16) + endY * t
      positions.setXYZ(index, x, y, 0)
    }
    positions.needsUpdate = true
    track.geometry.setDrawRange(0, Math.max(2, Math.floor(count * amount)))
  })
}

function updateScene(progress, elapsed) {
  const moleculeOpacity = 1 - THREE.MathUtils.smoothstep(progress, 0.5, 1.02)
  // Textual circuit, routing, and energy overlays supersede these old abstract meshes.
  const circuitOpacity = 0
  const qpuOpacity = 0
  const energyOpacity = 0
  const energyProgress = 0
  setGroupOpacity(moleculeGroup, moleculeOpacity)
  setGroupOpacity(circuitGroup, circuitOpacity)
  setGroupOpacity(qpuGroup, qpuOpacity)
  setGroupOpacity(energyGroup, energyOpacity)
  updateEnergyTracks(energyProgress)

  moleculeGroup.rotation.y = reducedMotion.value ? 0.38 : elapsed * 0.13
  moleculeGroup.rotation.x = 0.22
  circuitGroup.position.z = -0.18 * (1 - circuitOpacity)
  qpuGroup.rotation.y = compactLayout ? 0 : (reducedMotion.value ? 0.04 : Math.sin(elapsed * 0.35) * 0.025)
  energyGroup.position.y = -0.04 + (1 - energyOpacity) * 0.1
  camera.position.x = compactLayout ? 0 : Math.sin(progress * 0.8) * 0.18
  camera.position.y = compactLayout ? 0.05 : 0.16 + Math.cos(progress * 0.7) * 0.08
  camera.position.z = cameraBaseZ
  camera.lookAt(compactLayout ? 0.25 : 0.5, 0, 0)
}

function renderFrame(time = 0) {
  if (!renderer || !scene || !camera || !visible) return
  const rect = sectionRef.value?.getBoundingClientRect()
  const scrollProgress = rect ? THREE.MathUtils.clamp((-rect.top) / Math.max(sectionRef.value.offsetHeight - window.innerHeight, 1), 0, 1) : 0
  const stageProgress = scrollProgress * (stages.length - 1)
  activeStage.value = Math.min(stages.length - 1, Math.floor(stageProgress + 0.08))
  updateScene(stageProgress, time * 0.001)
  renderer.render(scene, camera)
  animationFrame = window.requestAnimationFrame(renderFrame)
}

function handleResize() {
  if (!renderer || !camera || !canvasRef.value) return
  const width = canvasRef.value.clientWidth || window.innerWidth
  const height = canvasRef.value.clientHeight || window.innerHeight
  camera.aspect = width / Math.max(height, 1)
  camera.updateProjectionMatrix()
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8))
  renderer.setSize(width, height, false)
}

function updateMotionPreference(event) {
  reducedMotion.value = event.matches
}

onMounted(() => {
  mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.value = mediaQuery.matches
  mediaQuery.addEventListener?.('change', updateMotionPreference)
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvasRef.value, antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' })
    renderer.setClearColor(color.warm, 1)
    buildScene()
    handleResize()
    started = true
  } catch (error) {
    fallback.value = true
    canvasRef.value?.setAttribute('aria-label', '静态 (LiH)₄ 场景降级')
  }
  resizeObserver = new ResizeObserver(handleResize)
  resizeObserver.observe(sectionRef.value)
  intersectionObserver = new IntersectionObserver(entries => {
    visible = entries[0]?.isIntersecting ?? true
    if (visible && started && !animationFrame) animationFrame = window.requestAnimationFrame(renderFrame)
    if (!visible && animationFrame) {
      window.cancelAnimationFrame(animationFrame)
      animationFrame = undefined
    }
  }, { threshold: 0.02 })
  intersectionObserver.observe(sectionRef.value)
  scrollHandler = () => {
    if (!animationFrame && visible && started) animationFrame = window.requestAnimationFrame(renderFrame)
  }
  window.addEventListener('scroll', scrollHandler, { passive: true })
  animationFrame = window.requestAnimationFrame(renderFrame)
})

onBeforeUnmount(() => {
  if (animationFrame) window.cancelAnimationFrame(animationFrame)
  window.removeEventListener('scroll', scrollHandler)
  mediaQuery?.removeEventListener?.('change', updateMotionPreference)
  resizeObserver?.disconnect()
  intersectionObserver?.disconnect()
  scene?.traverse(object => {
    object.geometry?.dispose?.()
    if (Array.isArray(object.material)) object.material.forEach(material => material.dispose())
    else object.material?.dispose?.()
  })
  renderer?.dispose?.()
})
</script>

<style scoped>
.narrative { position: relative; height: 400vh; background: #e7eae4; color: #17201d; }
.narrative-pin { height: 100vh; min-height: 640px; position: sticky; top: 0; overflow: hidden; isolation: isolate; }
.narrative-canvas { width: 100%; height: 100%; display: block; }
.scene-fallback { display: none; position: absolute; inset: 0; pointer-events: none; }.is-fallback .scene-fallback { display: block; }
.fallback-atoms { position: absolute; inset: 18% 12%; }.fallback-atom { width: clamp(34px, 5vw, 58px); aspect-ratio: 1; position: absolute; z-index: 1; display: grid; place-items: center; border: 1px solid #71866f; border-radius: 50%; background: #b8c1ba; color: #17201d; font: 700 .7rem ui-monospace, monospace; transform: translate(-50%, -50%); }.fallback-atom.h { width: clamp(22px, 3vw, 36px); background: #f6f7f1; }.fallback-edge { height: 1px; position: absolute; z-index: 0; background: #6f914f; opacity: .65; transform-origin: left; }
.narrative-topline { position: absolute; top: 8vh; left: clamp(24px, 6vw, 96px); right: clamp(24px, 6vw, 96px); display: flex; justify-content: space-between; color: #64736a; font: 700 .64rem ui-monospace, monospace; letter-spacing: .08em; }.scene-index { color: #6f914f; }
.narrative-copy { position: absolute; z-index: 1; left: clamp(24px, 6vw, 96px); top: 21vh; max-width: 640px; min-height: 130px; }.narrative-stage { width: min(80vw, 640px); margin: 0; position: absolute; color: #17201d; font-size: clamp(2.8rem, 6vw, 7rem); line-height: .94; letter-spacing: 0; font-weight: 700; opacity: 0; visibility: hidden; transform: translateY(14px); transition: opacity .22s ease, transform .25s ease; text-wrap: balance; }.narrative-stage.active { opacity: 1; visibility: visible; transform: translateY(0); }
.narrative-metrics { position: absolute; z-index: 1; left: clamp(24px, 6vw, 96px); right: clamp(24px, 6vw, 96px); bottom: 10vh; display: grid; grid-template-columns: repeat(3, minmax(120px, 190px)); border-top: 1px solid rgba(23,32,29,.24); }.narrative-metric { min-height: 78px; padding: 14px 14px 0 0; border-right: 1px solid rgba(23,32,29,.16); }.narrative-metric + .narrative-metric { padding-left: 14px; }.narrative-metric:last-child { border-right: 0; }.narrative-metric span { display: block; color: #59675e; font-size: .64rem; }.narrative-metric strong { display: block; margin-top: 8px; color: #17201d; font: 700 1.12rem ui-monospace, monospace; }.narrative-metric small { display: block; margin-top: 3px; color: #819087; font: .58rem ui-monospace, monospace; }
.narrative-disclaimer { position: absolute; z-index: 1; right: clamp(24px, 6vw, 96px); top: 16vh; max-width: 230px; color: #526059; font-size: .72rem; line-height: 1.55; text-align: right; }.scroll-cue { position: absolute; z-index: 1; right: clamp(24px, 6vw, 96px); bottom: 6vh; color: #6f914f; font: 700 .58rem ui-monospace, monospace; letter-spacing: .08em; }.scroll-cue b { margin-left: 8px; font-size: 1rem; }
.semantic-scene { position: absolute; z-index: 1; color: #17201d; pointer-events: none; }
.diagram-kicker { margin: 0 0 12px; color: #6f914f; font: 700 .6rem ui-monospace, monospace; letter-spacing: .12em; }
.diagram-placeholder { margin: 13px 0 0; color: #748279; font: 600 .62rem ui-monospace, monospace; letter-spacing: .04em; }

.quantum-circuit-diagram { top: 29vh; right: clamp(24px, 6vw, 96px); width: min(47vw, 660px); }
.circuit-body { position: relative; padding: 13px 0 10px; border-top: 1px solid rgba(23, 32, 29, .25); border-bottom: 1px solid rgba(23, 32, 29, .25); }
.circuit-row { display: grid; grid-template-columns: 43px minmax(0, 1fr); align-items: center; height: 55px; }
.qubit-label { color: #526259; font: 700 .7rem ui-monospace, monospace; }
.circuit-wire { height: 1px; position: relative; background: #45564b; }
.gate { width: 51px; height: 31px; position: absolute; top: -15px; z-index: 2; display: grid; place-items: center; box-sizing: border-box; border: 1px solid #52733e; background: #eff2e9; color: #243329; font: 700 .67rem ui-monospace, monospace; font-style: normal; white-space: nowrap; }
.gate-x { left: 8%; }.gate-ry { left: 28%; width: 68px; }.gate-ry-middle { left: 29%; }.gate-ry-lower { left: 26%; }
.cx-link { position: absolute; z-index: 3; display: flex; flex-direction: column; align-items: center; color: #17201d; font-style: normal; }
.cx-link i { width: 22px; height: 22px; display: grid; place-items: center; background: #e7eae4; color: #17201d; font: 700 1.18rem/1 ui-monospace, monospace; font-style: normal; }
.cx-link b { width: 1px; flex: 1; background: #17201d; }.cx-link-one { left: 70%; top: 20px; height: 57px; }.cx-link-two { left: 88%; top: 75px; height: 57px; }
.cx-target { font-size: 1.35rem !important; }

.virtual-qpu-diagram { top: 43vh; left: clamp(24px, 6vw, 96px); right: clamp(24px, 6vw, 96px); }
.qpu-cluster { position: relative; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: clamp(18px, 2.4vw, 42px); padding-bottom: 31px; }
.virtual-chip { min-width: 0; border: 1px solid #526259; background: rgba(246, 247, 241, .4); box-shadow: inset 0 0 0 5px rgba(111, 145, 79, .05); }
.virtual-chip header { padding: 9px 11px 8px; border-bottom: 1px solid rgba(23, 32, 29, .2); color: #27372c; font: 700 .66rem ui-monospace, monospace; letter-spacing: .04em; }
.chip-board { height: 132px; position: relative; overflow: hidden; }
.topology-frame { position: absolute; inset: 12px 18px 12px; }
.physical-coupling { height: 1px; position: absolute; z-index: 0; background: #728779; transform-origin: left center; }.coupling-top-a { width: 29%; left: 16%; top: 27%; }.coupling-top-b { width: 29%; left: 50%; top: 27%; }.coupling-bottom-a { width: 29%; left: 16%; top: 73%; }.coupling-bottom-b { width: 29%; left: 50%; top: 73%; }.coupling-vertical { width: 1px; height: 46%; left: 32.5%; top: 27%; }.coupling-vertical-mid { width: 1px; height: 46%; left: 66.5%; top: 27%; }.coupling-vertical-end { width: 1px; height: 46%; left: 83%; top: 27%; }
.physical-node { width: 25px; height: 25px; position: absolute; z-index: 1; display: grid; place-items: center; border: 1px solid #53733f; border-radius: 50%; background: #f6f7f1; color: #40523f; font: 700 .47rem ui-monospace, monospace; font-style: normal; transform: translate(-50%, -50%); }.node-top-a { left: 16%; top: 27%; }.node-top-b { left: 50%; top: 27%; }.node-top-c { left: 83%; top: 27%; }.node-bottom-a { left: 16%; top: 73%; }.node-bottom-b { left: 50%; top: 73%; }.node-bottom-c { left: 83%; top: 73%; }
.chip-local-circuit { position: absolute; z-index: 2; left: 5%; top: 3px; display: flex; align-items: center; gap: 4px; }.chip-local-circuit b { min-width: 28px; height: 22px; display: grid; place-items: center; border: 1px solid #6f914f; background: #edf1e8; color: #243329; font: 700 .55rem ui-monospace, monospace; }.chip-local-cx { left: 66.5%; top: 27%; flex-direction: column; gap: 0; transform: translate(-50%, -50%); }.chip-local-cx i { width: 1px; height: 21px; background: #17201d; }.chip-local-cx .local-control, .chip-local-cx .local-target { min-width: 19px; width: 19px; height: 19px; border: 0; border-radius: 50%; background: #e7eae4; font-size: .85rem; }
.chip-route { position: absolute; z-index: 3; left: 26%; top: 50%; display: flex; align-items: center; gap: 3px; color: #5d7d35; font: 700 .5rem ui-monospace, monospace; }.chip-route i { width: 22px; height: 22px; display: grid; place-items: center; border: 1px dashed #83a142; border-radius: 50%; background: #edf3e8; font: 700 1rem/1 ui-monospace, monospace; font-style: normal; }.chip-route b { font-weight: 700; }
.virtual-chip footer { padding: 8px 11px; border-top: 1px solid rgba(23, 32, 29, .16); color: #637167; font: 600 .55rem ui-monospace, monospace; }
.inter-chip-communication { position: absolute; z-index: 3; left: 15%; right: 15%; bottom: 0; display: grid; grid-template-columns: 1fr auto auto 1fr; align-items: center; gap: 6px; color: #587e35; font: 700 .56rem ui-monospace, monospace; white-space: nowrap; }.inter-chip-communication i { height: 1px; border-top: 1px dashed #81a354; }.inter-chip-communication b, .inter-chip-communication small { padding: 0 3px; background: #e7eae4; }.inter-chip-communication small { font: inherit; }

.energy-consistency-instrument { top: 36vh; right: clamp(24px, 6vw, 96px); width: min(52vw, 760px); }
.energy-panel { padding: 17px 18px 15px; border-top: 1px solid rgba(23, 32, 29, .3); border-bottom: 1px solid rgba(23, 32, 29, .3); }
.energy-reading { display: grid; grid-template-columns: minmax(150px, 1.1fr) minmax(88px, .7fr) auto; align-items: center; gap: 13px; min-height: 46px; color: #46564b; font: 600 .72rem ui-monospace, monospace; }.energy-reading strong { color: #17201d; font: 700 .78rem ui-monospace, monospace; white-space: nowrap; }.energy-channel { height: 1px; position: relative; background: #64756a; }.baseline-a::after, .baseline-b::after { content: ''; width: 9px; height: 9px; position: absolute; right: 0; top: -4px; border-radius: 50%; background: #6f914f; }.baseline-b::after { background: #b5f04c; }
.energy-alignment { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 9px; margin: 1px 0; color: #52733e; }.energy-alignment i { height: 1px; background: #52733e; }.energy-check { width: 28px; height: 28px; display: grid; place-items: center; border: 1px solid #52733e; border-radius: 50%; background: #edf3e8; font: 700 .9rem ui-monospace, monospace; }.energy-alignment span { grid-column: 1 / -1; margin-top: -2px; color: #6e7c72; text-align: center; font: 600 .55rem ui-monospace, monospace; }.error-reading { margin-top: 4px; border-top: 1px solid rgba(23, 32, 29, .12); }
.is-reduced-motion .narrative-stage { transition: none; }.is-reduced-motion .scroll-cue b { opacity: .55; }
@media (max-width: 620px) { .narrative { height: 400vh; }.narrative-pin { min-height: 560px; }.narrative-topline { top: 5vh; }.narrative-copy { top: 22vh; }.narrative-stage { width: calc(100vw - 48px); font-size: clamp(2.45rem, 13vw, 4rem); }.narrative-disclaimer { top: 12vh; right: 24px; max-width: 178px; }.narrative-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); bottom: 7vh; }.narrative-metric { min-height: 64px; border-right: 0; border-bottom: 1px solid rgba(23,32,29,.12); }.scroll-cue { display: none; }
  .semantic-scene { left: 24px; right: 24px; width: auto; }.diagram-kicker { margin-bottom: 8px; }.quantum-circuit-diagram { top: 39vh; }.circuit-row { height: 43px; grid-template-columns: 34px minmax(0, 1fr); }.gate { width: 38px; height: 25px; top: -12px; font-size: .52rem; }.gate-ry { width: 56px; }.cx-link-one { left: 69%; top: 14px; height: 45px; }.cx-link-two { left: 87%; top: 57px; height: 45px; }.cx-link i { width: 17px; height: 17px; font-size: .9rem; }.cx-target { font-size: 1.05rem !important; }
  .virtual-qpu-diagram { top: 37vh; }.qpu-cluster { grid-template-columns: 1fr; gap: 7px; padding-bottom: 23px; }.virtual-chip { display: grid; grid-template-columns: 112px 1fr; }.virtual-chip header { display: flex; align-items: center; padding: 7px; border-right: 1px solid rgba(23, 32, 29, .2); border-bottom: 0; font-size: .57rem; }.chip-board { height: 76px; }.topology-frame { inset: 8px 16px; }.physical-node { transform: translate(-50%, -50%) scale(.72); transform-origin: center; }.chip-local-circuit { top: 1px; }.chip-local-cx { top: 50%; }.chip-route { top: 50%; transform: translateY(-50%) scale(.8); transform-origin: left center; }.virtual-chip footer { display: none; }.inter-chip-communication { left: 12%; right: 12%; font-size: .5rem; }.energy-consistency-instrument { top: 40vh; }.energy-panel { padding: 11px 0 9px; }.energy-reading { grid-template-columns: minmax(132px, 1fr) minmax(54px, .55fr) auto; gap: 7px; min-height: 37px; font-size: .58rem; }.energy-reading strong { font-size: .63rem; }.energy-check { width: 24px; height: 24px; }.narrative-metrics:has(.narrative-metric:nth-child(3)) { grid-template-columns: repeat(3, minmax(0, 1fr)); }.narrative-metrics:has(.narrative-metric:nth-child(3)) .narrative-metric { padding-left: 5px; padding-right: 5px; font-size: .55rem; }.narrative-metrics:has(.narrative-metric:nth-child(3)) .narrative-metric strong { font-size: .86rem; } }
@media (prefers-reduced-motion: reduce) { .narrative-stage { transition: none; } }
</style>

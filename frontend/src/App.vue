<!-- 文件基本信息：frontend/src/App.vue
用途：真实 API 驱动的项目绑定、训练、评价、结果查看和下载页面。
输入：用户填写的 HFSS 绝对路径、阵列 JSON 和模式选择；后端任务/结果响应。
输出：项目状态、任务状态、总阵结果数据预览和下载动作。
维护：修改页面状态时同步 UI 验收场景、API client、目录索引和 E2E 测试。
-->
<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, saveTaskDownload } from './api/client'

const projects = ref([])
const activeProjectId = ref('')
const hfssPath = ref('')
const inputText = ref('')
const modes = ref(['prediction'])
const task = ref(null)
const result = ref(null)
const busy = ref(false)
const errorMessage = ref('')
const notice = ref('')
let pollTimer = null

const activeProject = computed(() => projects.value.find((item) => item.project_id === activeProjectId.value) || null)
const canPredict = computed(() => activeProject.value?.model_status === 'ready')
const canValidate = computed(() => Boolean(activeProject.value))
const terminal = computed(() => task.value && !['queued', 'running'].includes(task.value.status))

function chartPoints(records, field) {
  const cut = (records || []).filter((record) => Number(record['Theta[deg]']) === 0).sort((a, b) => Number(a['Phi[deg]']) - Number(b['Phi[deg]']))
  if (!cut.length) return ''
  const values = cut.map((record) => Number(record[field]))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  return cut.map((record, index) => {
    const x = (index / Math.max(cut.length - 1, 1)) * 560 + 20
    const y = 180 - ((Number(record[field]) - min) / span) * 150
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
}

function showError(error) {
  errorMessage.value = error?.message || String(error)
}

async function loadProjects() {
  try {
    const data = await api.listProjects()
    projects.value = data.items || []
    if (!activeProjectId.value && projects.value.length) activeProjectId.value = projects.value[0].project_id
  } catch (error) {
    showError(error)
  }
}

async function bindProject() {
  if (!hfssPath.value.trim()) return showError(new Error('请输入 HFSS .aedt 工程绝对路径'))
  busy.value = true
  errorMessage.value = ''
  try {
    const created = await api.createProject(hfssPath.value.trim())
    activeProjectId.value = created.project_id
    notice.value = '工程绑定成功，等待开始训练。'
    await loadProjects()
  } catch (error) {
    showError(error)
  } finally {
    busy.value = false
  }
}

async function startTraining() {
  if (!activeProject.value) return showError(new Error('请先绑定工程'))
  busy.value = true
  errorMessage.value = ''
  try {
    const created = await api.startTraining(activeProject.value.project_id)
    await pollTask(created.task_id)
    await loadProjects()
  } catch (error) {
    showError(error)
  } finally {
    busy.value = false
  }
}

function toggleMode(mode) {
  if (modes.value.includes(mode)) {
    if (modes.value.length > 1) modes.value = modes.value.filter((item) => item !== mode)
  } else {
    modes.value = [...modes.value, mode]
  }
}

async function evaluate() {
  if (!activeProject.value) return showError(new Error('请先绑定工程'))
  if (!modes.value.length) return showError(new Error('至少选择预测或验证一种模式'))
  let input
  try {
    input = JSON.parse(inputText.value)
  } catch {
    return showError(new Error('阵列输入必须是合法 JSON'))
  }
  busy.value = true
  errorMessage.value = ''
  result.value = null
  try {
    const created = await api.createEvaluation(activeProject.value.project_id, input, modes.value)
    await pollTask(created.task_id)
    if (task.value?.result_available) result.value = await api.getResults(created.task_id)
  } catch (error) {
    showError(error)
  } finally {
    busy.value = false
  }
}

function pollTask(taskId) {
  return new Promise((resolve, reject) => {
    if (pollTimer) clearInterval(pollTimer)
    const tick = async () => {
      try {
        task.value = await api.getTask(taskId)
        if (!['queued', 'running'].includes(task.value.status)) {
          clearInterval(pollTimer)
          pollTimer = null
          resolve(task.value)
        }
      } catch (error) {
        clearInterval(pollTimer)
        pollTimer = null
        reject(error)
      }
    }
    tick()
    pollTimer = setInterval(tick, 1000)
  })
}

onMounted(loadProjects)
onUnmounted(() => pollTimer && clearInterval(pollTimer))
</script>

<template>
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">ArrayLab · 真实 API 工作台</p>
        <h1>非规则阵列方向图预测</h1>
        <p class="subtitle">通过后端任务接口执行训练、预测、验证和结果下载。</p>
      </div>
      <span class="connection">{{ busy ? '任务处理中' : '就绪' }}</span>
    </header>

    <section class="grid two-columns">
      <article class="card">
        <h2>项目与 HFSS 工程</h2>
        <label>已有项目</label>
        <select v-model="activeProjectId">
          <option value="">请选择项目</option>
          <option v-for="project in projects" :key="project.project_id" :value="project.project_id">
            {{ project.project_name }} · {{ project.model_status }}
          </option>
        </select>
        <label for="hfss-path">HFSS 工程绝对路径</label>
        <input id="hfss-path" v-model="hfssPath" placeholder="例如：E:\\projects\\array.aedt" />
        <button class="secondary" :disabled="busy" @click="bindProject">绑定工程</button>
        <p v-if="activeProject" class="meta">{{ activeProject.hfss_project_name }} · 模型：{{ activeProject.model_status }}</p>
        <button class="primary" :disabled="busy || !activeProject" @click="startTraining">开始训练</button>
      </article>

      <article class="card">
        <h2>阵列输入与评价</h2>
        <label for="array-input">固定 JSON 输入（JSON 是权威来源）</label>
        <textarea id="array-input" v-model="inputText" rows="11" placeholder='{"unit_count":1,"units":[{"unit_id":1,"i":1,"j":1,"x":0,"y":0}]}' />
        <div class="modes">
          <button :class="{ selected: modes.includes('prediction') }" @click="toggleMode('prediction')">预测</button>
          <button :class="{ selected: modes.includes('validation') }" @click="toggleMode('validation')">验证</button>
        </div>
        <p v-if="!canPredict && modes.includes('prediction')" class="hint">预测需要训练成功的模型。</p>
        <p v-if="!canValidate && modes.includes('validation')" class="hint">验证需要已绑定工程。</p>
        <button class="primary" :disabled="busy || !activeProject" @click="evaluate">执行所选任务</button>
      </article>
    </section>

    <section class="card task-card">
      <div class="row-between"><h2>任务状态</h2><span v-if="task" class="status">{{ task.status }}</span></div>
      <p v-if="task">{{ task.task_id }} · {{ task.current_stage }} · {{ task.message || '—' }}</p>
      <p v-else class="hint">尚未创建任务。</p>
      <div v-if="task" class="branches">
        <span>预测：{{ task.prediction_status || '未选择' }}</span>
        <span>验证：{{ task.validation_status || '未选择' }}</span>
      </div>
    </section>

    <section v-if="result" class="card">
      <div class="row-between"><h2>总阵结果</h2><button class="secondary" @click="saveTaskDownload(task.task_id)">下载完整结果</button></div>
      <p class="meta">模式：{{ result.mode }} · 结果文件：{{ result.files?.length || 0 }} 个</p>
      <div v-for="(pattern, mode) in result.total_array_result" :key="mode" class="result-block">
        <h3>{{ mode }}</h3>
        <p>采样点：{{ pattern?.records?.length || 0 }}；字段：Phi、Theta、ECP 幅度、ECP 相位。</p>
        <div class="charts" aria-label="总阵方向图">
          <div class="chart-card">
            <h4>总阵幅度 · Theta=0°</h4>
            <svg viewBox="0 0 600 200" role="img" aria-label="总阵幅度图">
              <polyline :points="chartPoints(pattern?.records, 'ECP_dB')" fill="none" stroke="#245bd6" stroke-width="2" />
            </svg>
          </div>
          <div class="chart-card">
            <h4>总阵相位 · Theta=0°</h4>
            <svg viewBox="0 0 600 200" role="img" aria-label="总阵相位图">
              <polyline :points="chartPoints(pattern?.records, 'ECP_Phase_deg')" fill="none" stroke="#d65b45" stroke-width="2" />
            </svg>
          </div>
        </div>
        <pre>{{ JSON.stringify(pattern?.records?.slice(0, 3), null, 2) }}</pre>
      </div>
    </section>

    <p v-if="notice" class="notice">{{ notice }}</p>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    <p v-if="terminal && task?.status === 'partial_success'" class="hint">一个分支成功、另一个分支失败；页面保留成功分支结果，不生成完整对比结果。</p>
  </main>
</template>

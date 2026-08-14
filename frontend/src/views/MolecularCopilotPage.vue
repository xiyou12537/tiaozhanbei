<template>
  <div class="copilot-page">
    <header class="copilot-hero">
      <div>
        <span class="page-kicker">MOLECULAR COPILOT / CONTROLLED ASSISTANCE</span>
        <h2>分子计算的对话式工作台</h2>
        <p>解释平台能力、读取当前用户结果，并在创建任务前生成可审阅的草稿。</p>
      </div>
      <div class="boundary-badges" aria-label="计算边界"><el-tag>logical_virtual_qpu</el-tag><el-tag type="warning">非真实 QPU</el-tag></div>
    </header>

    <section class="execution-boundary"><strong>固定能力边界</strong><p>Copilot 只能协助当前用户使用分子计算平台。所有执行均为 logical_virtual_qpu 逻辑虚拟 QPU 模拟，is_real_qpu=false；不会调用真实量子硬件。</p></section>

    <section class="data-boundary" data-testid="copilot-data-boundary" aria-label="第三方模型数据边界">
      <div class="data-boundary-lead"><span>THIRD-PARTY DATA BOUNDARY</span><h3>数据如何处理</h3><p>{{ assistantDataBoundary.summary }}</p></div>
      <details data-testid="copilot-data-details">
        <summary>查看会发送什么与不会发送什么</summary>
        <div class="data-boundary-details">
          <section><h4>会发送什么</h4><ul><li v-for="item in assistantDataBoundary.sent" :key="item">{{ item }}</li></ul></section>
          <section><h4>不会发送什么</h4><ul><li v-for="item in assistantDataBoundary.excluded" :key="item">{{ item }}</li></ul></section>
          <section class="data-boundary-control"><h4>模型权限与任务确认</h4><p v-for="item in assistantDataBoundary.controls" :key="item">{{ item }}</p></section>
        </div>
      </details>
    </section>

    <el-alert v-if="displayError" class="copilot-error" type="error" :closable="false" show-icon :title="displayError">
      <el-button v-if="canRetry" data-testid="copilot-retry" size="small" :disabled="sending || initializing" @click="retry">重试</el-button>
    </el-alert>

    <section class="copilot-workbench">
      <main class="conversation-panel" aria-live="polite">
        <header><div><span>SESSION</span><strong>{{ sessionId || '正在建立会话' }}</strong></div><small>{{ initializing ? '正在恢复或创建当前用户会话…' : '会话仅在当前账号下恢复' }}</small></header>
        <div class="conversation-scroll">
          <div v-if="!messages.length && !state.streamingText" class="empty-conversation"><span>READY / 01</span><h3>从一个问题开始</h3><p>Copilot 不会绕过确认直接创建 Workflow、Study 或 Bond Scan。</p></div>
          <article v-for="message in messages" :key="message.message_id" class="message" :class="message.role === 'user' ? 'user-message' : 'assistant-message'" :data-testid="message.role === 'assistant' ? 'assistant-message-final' : 'user-message'">
            <span>{{ message.role === 'user' ? 'YOU' : 'COPILOT' }}</span><p>{{ message.content }}</p>
          </article>
          <article v-if="state.streamingText" data-testid="copilot-partial" class="message assistant-message partial-message"><span>COPILOT / STREAMING</span><p>{{ state.streamingText }}</p><small>未完成的流式内容</small></article>
        </div>

        <div class="suggested-prompts" aria-label="初始引导问题">
          <button v-for="prompt in prompts" :key="prompt" type="button" :disabled="sending || initializing" @click="sendPrompt(prompt)">{{ prompt }}</button>
        </div>
        <form class="composer" @submit.prevent="send">
          <label for="copilot-input">向 Molecular Copilot 提问</label>
          <textarea id="copilot-input" ref="inputRef" v-model="input" data-testid="copilot-input" rows="3" maxlength="4000" :disabled="sending || initializing" placeholder="例如：我应该选择哪种分子计算任务？" @keydown="submitWithShortcut" />
          <div><small>Ctrl / ⌘ + Enter 发送 · 回答仅按纯文本显示</small><el-button data-testid="copilot-send" native-type="submit" type="primary" :loading="sending" :disabled="!input.trim() || initializing">发送</el-button></div>
        </form>
      </main>

      <aside class="execution-panel" aria-label="受控工具执行过程">
        <header><span>TOOL LEDGER</span><h3>受控执行记录</h3><p>读取工具仅展示结果；草稿工具需要明确确认。</p></header>
        <div v-if="!state.toolExecutions.length" class="empty-tools">尚无工具执行记录</div>
        <article v-for="execution in state.toolExecutions" :key="execution.execution_id || `${execution.tool_name}-${execution.status}`" class="tool-execution" :data-testid="`tool-execution-${execution.execution_id || execution.tool_name}`">
          <div class="tool-head"><strong>{{ toolLabel(execution.tool_name) }}</strong><el-tag :type="toolTagType(execution.status)">{{ toolStatus(execution.status) }}</el-tag></div>
          <p>{{ execution.tool_kind === 'draft' ? '已生成任务草稿，尚未创建计算任务。' : '已完成受控读取，不包含真实 QPU 调度。' }}</p>
          <small v-if="execution.parameter_summary">{{ execution.parameter_summary }}</small>

          <section v-if="execution.tool_kind === 'draft' && execution.status === 'pending_confirmation' && !deferred.has(execution.execution_id)" class="draft-card" :data-testid="`draft-confirmation-${execution.execution_id}`">
            <span>CONFIRMATION REQUIRED</span><p>有效期：{{ formatTime(execution.confirmation_expires_at) }}</p>
            <el-alert v-if="confirmationErrors[execution.execution_id]" type="error" :closable="false" :title="confirmationErrors[execution.execution_id]" />
            <div><el-button :data-testid="`confirm-${execution.execution_id}`" type="primary" size="small" :loading="confirming.has(execution.execution_id)" :disabled="confirming.has(execution.execution_id)" @click="confirmDraft(execution)">确认创建任务</el-button><el-button size="small" :disabled="confirming.has(execution.execution_id)" @click="deferDraft(execution.execution_id)">暂不执行</el-button></div>
          </section>
          <p v-else-if="execution.tool_kind === 'draft' && deferred.has(execution.execution_id)" class="deferred">草稿仍待确认；本次不会创建任务。<button type="button" @click="restoreDraft(execution.execution_id)">重新查看</button></p>
          <router-link v-if="taskLink(execution)" :data-testid="`confirmed-task-${execution.execution_id}`" class="task-link" :to="taskLink(execution)">查看 {{ taskLabel(execution.result.task_type) }} · {{ execution.result.task_id }}</router-link>
        </article>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { createAssistantSession, confirmAssistantTool, getAssistantSession, streamAssistantMessage } from '../api/assistantApi.js'
import { readUser } from '../services/authStorage.js'
import { clearRecentAssistantSession, readRecentAssistantSession, saveRecentAssistantSession } from '../services/assistantSessionStorage.js'
import { assistantErrorMessage, assistantTaskLink, createAssistantConversationState, reduceAssistantSseEvent } from '../services/assistantSseService.js'
import { assistantDataBoundary } from '../services/assistantDataBoundary.js'

const prompts = ['这个平台能做什么', '我应该选择哪种任务', '如何理解 Bond Scan']
const input = ref('')
const inputRef = ref(null)
const sessionId = ref('')
const state = ref(createAssistantConversationState())
const initializing = ref(false)
const sending = ref(false)
const requestError = ref(null)
const lastMessage = ref('')
const confirming = ref(new Set())
const deferred = ref(new Set())
const confirmationErrors = ref({})
let abortController = null

const messages = computed(() => state.value.messages)
const displayError = computed(() => requestError.value ? errorText(requestError.value) : state.value.streamError ? errorText(state.value.streamError) : '')
const canRetry = computed(() => Boolean(requestError.value || state.value.streamError))

onMounted(initialize)
onBeforeUnmount(() => abortController?.abort())

async function initialize() {
  initializing.value = true
  requestError.value = null
  const user = readUser()
  const savedSessionId = readRecentAssistantSession(user)
  try {
    const session = savedSessionId ? await getAssistantSession(savedSessionId) : await createAssistantSession()
    sessionId.value = session.session_id
    saveRecentAssistantSession(user, session.session_id)
    state.value = { ...createAssistantConversationState(), messages: session.messages || [], toolExecutions: session.tool_executions || [] }
  } catch (error) {
    if (savedSessionId && error?.response?.status === 404) {
      clearRecentAssistantSession(user)
      try {
        const session = await createAssistantSession()
        sessionId.value = session.session_id
        saveRecentAssistantSession(user, session.session_id)
      } catch (createError) { requestError.value = createError }
    } else requestError.value = error
  } finally { initializing.value = false }
}

async function send() { await sendPrompt(input.value) }

async function sendPrompt(prompt) {
  const message = prompt.trim()
  if (!message || sending.value || initializing.value || !sessionId.value) return
  input.value = ''
  lastMessage.value = message
  requestError.value = null
  state.value = { ...state.value, messages: [...state.value.messages, { message_id: `local-${Date.now()}`, role: 'user', content: message, created_at: null }], streamingText: '', streamError: null, done: false }
  sending.value = true
  abortController = new AbortController()
  try {
    await streamAssistantMessage(sessionId.value, message, {
      signal: abortController.signal,
      onEvent: event => { state.value = reduceAssistantSseEvent(state.value, event) },
    })
  } catch (error) {
    if (error?.name !== 'AbortError') requestError.value = error
  } finally {
    abortController = null
    sending.value = false
  }
}

function submitWithShortcut(event) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); send() }
}

async function confirmDraft(execution) {
  if (!execution.confirmation_id || confirming.value.has(execution.execution_id)) return
  const next = new Set(confirming.value)
  next.add(execution.execution_id)
  confirming.value = next
  confirmationErrors.value = { ...confirmationErrors.value, [execution.execution_id]: '' }
  try {
    const confirmed = await confirmAssistantTool(sessionId.value, {
      confirmation_id: execution.confirmation_id,
      tool_name: execution.tool_name,
      parameter_summary: execution.parameter_summary,
    })
    state.value = { ...state.value, toolExecutions: state.value.toolExecutions.map(item => item.execution_id === execution.execution_id ? { ...item, ...confirmed } : item) }
  } catch (error) {
    confirmationErrors.value = { ...confirmationErrors.value, [execution.execution_id]: errorText(error) }
  } finally {
    const remaining = new Set(confirming.value)
    remaining.delete(execution.execution_id)
    confirming.value = remaining
  }
}

function deferDraft(executionId) { deferred.value = new Set([...deferred.value, executionId]) }
function restoreDraft(executionId) { const next = new Set(deferred.value); next.delete(executionId); deferred.value = next }
function retry() { if (lastMessage.value && sessionId.value) sendPrompt(lastMessage.value); else initialize() }

function errorText(error) {
  const detail = error?.response?.data?.detail || error || {}
  return assistantErrorMessage(detail.code || error?.code)
}

function toolLabel(name) { return ({ platform_capabilities: '读取平台能力', select_task: '选择当前任务', get_current_user_result: '读取任务结果', draft_molecule_workflow: 'Workflow 草稿', draft_molecular_study: 'Molecular Study 草稿', draft_molecular_bond_scan: 'LiH Bond Scan 草稿' })[name] || name || '受控工具' }
function toolStatus(status) { return ({ running: '执行中', completed: '已完成', pending_confirmation: '待确认', confirmed: '已确认', failed: '失败', expired: '已过期' })[status] || status || '已接收' }
function toolTagType(status) { return ({ completed: 'success', pending_confirmation: 'warning', confirmed: 'success', failed: 'danger', expired: 'info' })[status] || 'info' }
function formatTime(value) { return value ? new Date(value).toLocaleString() : '以服务端记录为准' }
function taskLabel(type) { return ({ molecule_workflow: 'Workflow', molecular_study: 'Molecular Study', molecular_bond_scan: 'LiH Bond Scan' })[type] || '任务' }
function taskLink(execution) { return assistantTaskLink(execution.result) }
</script>

<style scoped>
.copilot-page{display:grid;gap:22px}.copilot-hero{min-height:210px;padding:34px;border:1px solid var(--lz-line);display:flex;align-items:flex-end;justify-content:space-between;gap:26px;background:#e8ebe5}.page-kicker,.execution-panel header>span,.conversation-panel>header span,.draft-card>span,.data-boundary-lead>span{color:#68756d;font:700 .67rem ui-monospace,monospace;letter-spacing:.12em}.copilot-hero h2{max-width:760px;margin:12px 0;font-size:clamp(2.25rem,5vw,4.5rem);line-height:.93;letter-spacing:-.07em}.copilot-hero p{margin:0;color:var(--lz-muted)}.boundary-badges{display:flex;flex-wrap:wrap;gap:8px}.execution-boundary{padding:16px 22px;display:flex;gap:24px;align-items:center;border:1px solid #3a4b40;background:#17201d;color:#e5eadf}.execution-boundary strong{color:#b5f04c;font:.74rem ui-monospace,monospace;white-space:nowrap}.execution-boundary p{margin:0;color:#bac4bc;line-height:1.55;font-size:.8rem}.data-boundary{padding:20px 22px;border:1px solid #b8c3b3;background:#f4f7f1}.data-boundary-lead{display:grid;gap:7px}.data-boundary h3{margin:0;font-size:1.2rem}.data-boundary p{margin:0;color:#526057;line-height:1.65;font-size:.82rem}.data-boundary details{margin-top:14px;border-top:1px solid #cfd8ca}.data-boundary summary{padding-top:13px;color:#3c6235;cursor:pointer;font-size:.82rem;font-weight:700}.data-boundary-details{display:grid;grid-template-columns:1fr 1fr;gap:1px;margin-top:13px;background:#d2dacd}.data-boundary-details section{padding:16px;background:#fff}.data-boundary-details h4{margin:0 0 9px;color:#52634f;font-size:.78rem}.data-boundary-details ul{margin:0;padding-left:18px;color:#627068;font-size:.76rem;line-height:1.7}.data-boundary-control{grid-column:1/-1}.data-boundary-control p+p{margin-top:8px}.copilot-error{margin:0}.copilot-workbench{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(310px,.6fr);align-items:start;gap:18px}.conversation-panel,.execution-panel{border:1px solid var(--lz-line);background:var(--lz-panel)}.conversation-panel>header{min-height:80px;padding:18px 22px;border-bottom:1px solid #dce0da;display:flex;align-items:center;justify-content:space-between;gap:18px}.conversation-panel>header div{display:grid;gap:5px}.conversation-panel>header strong{font:.72rem ui-monospace,monospace}.conversation-panel>header small{color:#758078;font-size:.72rem}.conversation-scroll{min-height:370px;max-height:590px;padding:22px;overflow:auto;display:grid;align-content:start;gap:12px;background:linear-gradient(90deg,rgba(98,140,61,.04) 1px,transparent 1px) 0 0/26px 26px}.empty-conversation{min-height:300px;padding:34px;display:grid;align-content:center;justify-items:start;background:#f4f6f1}.empty-conversation span{color:#73924f;font:700 .7rem ui-monospace,monospace}.empty-conversation h3{margin:14px 0 8px;font-size:2rem;letter-spacing:-.05em}.empty-conversation p{max-width:420px;margin:0;color:#68736c;line-height:1.7}.message{max-width:min(84%,680px);padding:14px 16px;border:1px solid #d5dbd3;display:grid;gap:8px;background:#fff}.message span{font:700 .64rem ui-monospace,monospace;letter-spacing:.1em}.message p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65;font-size:.86rem}.user-message{justify-self:end;border-color:#668e43;background:#edf4e8}.user-message span{color:#537436}.assistant-message{justify-self:start}.partial-message{border-color:#d5b65d;background:#fff9e7}.partial-message small{color:#80651d;font-size:.7rem}.suggested-prompts{padding:16px 22px;display:flex;flex-wrap:wrap;gap:8px;border-top:1px solid #e1e5df}.suggested-prompts button,.deferred button{border:1px solid #c5cec0;background:#f3f5f1;color:#426132;cursor:pointer}.suggested-prompts button{padding:7px 10px;font-size:.75rem}.suggested-prompts button:hover,.suggested-prompts button:focus-visible{border-color:#668e43;background:#e8f1e0}.composer{padding:20px 22px 22px;border-top:1px solid #dce0da;background:#fafbf8;display:grid;gap:8px}.composer label{font-weight:700;font-size:.85rem}.composer textarea{width:100%;resize:vertical;padding:12px;border:1px solid #bdc6bc;background:#fff;line-height:1.6}.composer textarea:focus{outline:2px solid #a8c68a;outline-offset:1px}.composer>div{display:flex;align-items:center;justify-content:space-between;gap:10px}.composer small{color:#728076;font-size:.7rem}.execution-panel>header{padding:24px;border-bottom:1px solid #dce0da;background:#17201d;color:#fff}.execution-panel h3{margin:10px 0;font-size:1.4rem}.execution-panel header p{margin:0;color:#adb9ae;font-size:.78rem;line-height:1.6}.empty-tools{padding:34px 24px;color:#778178;font-size:.82rem}.tool-execution{padding:18px 20px;border-bottom:1px solid #dfe3dd;display:grid;gap:10px}.tool-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.tool-head strong{font:.78rem ui-monospace,monospace;overflow-wrap:anywhere}.tool-execution>p{margin:0;color:#68736c;font-size:.78rem;line-height:1.55}.tool-execution>small{display:block;max-height:55px;overflow:auto;color:#68746c;font:.62rem/1.5 ui-monospace,monospace;overflow-wrap:anywhere}.draft-card{padding:13px;border:1px solid #d5b65d;background:#fff8df;display:grid;gap:7px}.draft-card>span{color:#896f21}.draft-card p,.deferred{margin:0;color:#675b35;font-size:.74rem;line-height:1.55}.draft-card>div{display:flex;flex-wrap:wrap;gap:8px}.deferred{padding:10px;background:#f4f5f1}.deferred button{margin-left:5px;padding:2px 5px}.task-link{padding:9px 10px;border:1px solid #668e43;background:#edf4e8;color:#355629;font-weight:700;font-size:.75rem;text-decoration:none;overflow-wrap:anywhere}.task-link:hover,.task-link:focus-visible{background:#dfeeda}@media(max-width:1000px){.copilot-workbench{grid-template-columns:1fr}.execution-panel{display:grid;grid-template-columns:1fr 1fr}.execution-panel>header,.empty-tools{grid-column:1/-1}.tool-execution{border-right:1px solid #dfe3dd}}@media(max-width:680px){.copilot-hero{align-items:flex-start;flex-direction:column;padding:24px}.execution-boundary{align-items:flex-start;flex-direction:column;padding:16px}.data-boundary{padding:18px}.data-boundary-details{grid-template-columns:1fr}.data-boundary-control{grid-column:auto}.conversation-panel>header{align-items:flex-start;flex-direction:column}.conversation-scroll{padding:14px;min-height:310px}.message{max-width:96%}.composer,.suggested-prompts{padding-left:14px;padding-right:14px}.composer>div{align-items:flex-start;flex-direction:column}.execution-panel{display:block}.tool-execution{border-right:0}}
</style>

<template>
  <section class="auth-card">
    <button v-if="showClose" class="auth-close" type="button" @click="$emit('close')" aria-label="关闭">
      <el-icon :size="18"><Close /></el-icon>
    </button>

    <div class="auth-card-head">
      <div class="auth-badge">MQ</div>
      <div>
        <span class="auth-kicker">Account Center</span>
        <h2>{{ headingTitle }}</h2>
        <p>{{ headingText }}</p>
      </div>
    </div>

    <div v-if="successMessage" class="form-success">
      <el-icon :size="18"><CircleCheck /></el-icon>
      <span>{{ successMessage }}</span>
    </div>

    <div class="auth-tabs" role="tablist">
      <button type="button" :class="{ active: activeTab === 'login' }" @click="switchTab('login')">登录</button>
      <button type="button" :class="{ active: activeTab === 'register' }" @click="switchTab('register')">注册</button>
    </div>

    <Transition name="auth-fade" mode="out-in">
      <form v-if="activeTab === 'login'" key="login" class="auth-form" @submit.prevent="handleLogin">
        <label class="field-label" for="login-username">用户名</label>
        <div class="form-field">
          <el-icon :size="18"><User /></el-icon>
          <input
            id="login-username"
            ref="loginUserInput"
            v-model.trim="loginForm.username"
            type="text"
            placeholder="输入你的账号名"
            autocomplete="username"
          />
        </div>

        <label class="field-label" for="login-password">密码</label>
        <div class="form-field">
          <el-icon :size="18"><Lock /></el-icon>
          <input
            id="login-password"
            v-model="loginForm.password"
            type="password"
            placeholder="输入登录密码"
            autocomplete="current-password"
          />
        </div>

        <div v-if="loginError" class="form-error">{{ loginError }}</div>

        <button type="submit" class="auth-submit" :disabled="loginLoading">
          <span v-if="!loginLoading">登录并进入系统</span>
          <el-icon v-else :size="18" class="loading-icon"><Loading /></el-icon>
        </button>
      </form>

      <form v-else key="register" class="auth-form" @submit.prevent="handleRegister">
        <label class="field-label" for="register-username">用户名</label>
        <div class="form-field">
          <el-icon :size="18"><User /></el-icon>
          <input
            id="register-username"
            ref="registerUserInput"
            v-model.trim="registerForm.username"
            type="text"
            placeholder="创建账号名"
            autocomplete="username"
          />
        </div>

        <label class="field-label" for="register-password">密码</label>
        <div class="form-field">
          <el-icon :size="18"><Lock /></el-icon>
          <input
            id="register-password"
            v-model="registerForm.password"
            type="password"
            placeholder="至少 6 位密码"
            autocomplete="new-password"
          />
        </div>

        <label class="field-label" for="register-confirm">确认密码</label>
        <div class="form-field">
          <el-icon :size="18"><Lock /></el-icon>
          <input
            id="register-confirm"
            v-model="registerForm.confirm"
            type="password"
            placeholder="再次输入密码"
            autocomplete="new-password"
          />
        </div>

        <div v-if="registerError" class="form-error">{{ registerError }}</div>

        <button type="submit" class="auth-submit" :disabled="registerLoading">
          <span v-if="!registerLoading">创建账号</span>
          <el-icon v-else :size="18" class="loading-icon"><Loading /></el-icon>
        </button>
      </form>
    </Transition>

    <div class="auth-helper">
      <strong>{{ helperTitle }}</strong>
      <p>{{ helperText }}</p>
    </div>

    <p class="auth-switch">
      <template v-if="activeTab === 'login'">
        还没有账号？
        <button type="button" class="switch-link" @click="switchTab('register')">去注册</button>
      </template>
      <template v-else>
        已有账号？
        <button type="button" class="switch-link" @click="switchTab('login')">返回登录</button>
      </template>
    </p>
  </section>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, Close, Loading, Lock, User } from '@element-plus/icons-vue'
import { registerUser } from '../api/authApi'
import { useAuth } from '../composables/useAuth'

const props = defineProps({
  initialTab: { type: String, default: 'login' },
  showClose: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'success', 'tab-change'])
const { login } = useAuth()

const activeTab = ref(normalizeTab(props.initialTab))
const loginUserInput = ref(null)
const registerUserInput = ref(null)

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', password: '', confirm: '' })

const loginLoading = ref(false)
const registerLoading = ref(false)
const loginError = ref('')
const registerError = ref('')
const successMessage = ref('')

const headingTitle = computed(() => (activeTab.value === 'login' ? '登录分子量子计算平台' : '创建平台账号'))
const headingText = computed(() =>
  activeTab.value === 'login'
    ? '登录后可新建分子计算、查询 Workflow 任务并查看可审计的模拟结果。'
    : '创建账号后会回到登录页，请使用刚才的用户名和密码登录系统。'
)
const helperTitle = computed(() => (activeTab.value === 'login' ? '登录说明' : '注册说明'))
const helperText = computed(() =>
  activeTab.value === 'login'
    ? '如果提示账号或密码错误，请核对输入；如果提示服务不可用，请确认后端认证接口已经启动。'
    : '注册成功后会自动切换到登录表单，并回填用户名，方便你确认后进入系统。'
)

watch(
  () => props.initialTab,
  value => {
    const nextTab = normalizeTab(value)
    if (activeTab.value !== nextTab) {
      activeTab.value = nextTab
      resetErrors()
      focusCurrentField()
    }
  },
  { immediate: true }
)

watch(activeTab, () => {
  resetErrors()
  focusCurrentField()
})

function normalizeTab(tab) {
  return tab === 'register' ? 'register' : 'login'
}

function switchTab(tab) {
  activeTab.value = normalizeTab(tab)
  successMessage.value = ''
  emit('tab-change', activeTab.value)
}

function resetErrors() {
  loginError.value = ''
  registerError.value = ''
}

function focusCurrentField() {
  nextTick(() => {
    if (activeTab.value === 'login') {
      loginUserInput.value?.focus()
      return
    }
    registerUserInput.value?.focus()
  })
}

async function handleLogin() {
  loginError.value = ''
  successMessage.value = ''

  if (!loginForm.username) {
    loginError.value = '请输入用户名。'
    return
  }
  if (!loginForm.password) {
    loginError.value = '请输入密码。'
    return
  }

  loginLoading.value = true
  try {
    await login(loginForm.username, loginForm.password)
    loginForm.username = ''
    loginForm.password = ''
    ElMessage.success('登录成功，正在进入工作台')
    emit('success', { mode: 'login' })
  } catch (error) {
    console.error('Login request failed', error)
    loginError.value = resolveAuthErrorMessage(error, 'login')
  } finally {
    loginLoading.value = false
  }
}

async function handleRegister() {
  registerError.value = ''
  successMessage.value = ''

  if (!registerForm.username) {
    registerError.value = '请输入用户名。'
    return
  }
  if (!registerForm.password) {
    registerError.value = '请输入密码。'
    return
  }
  if (registerForm.password.length < 6) {
    registerError.value = '密码至少需要 6 位。'
    return
  }
  if (registerForm.password !== registerForm.confirm) {
    registerError.value = '两次输入的密码不一致。'
    return
  }

  registerLoading.value = true
  try {
    const createdUsername = registerForm.username
    await registerUser(registerForm.username, registerForm.password)
    registerForm.username = ''
    registerForm.password = ''
    registerForm.confirm = ''
    loginForm.username = createdUsername
    loginForm.password = ''
    successMessage.value = `账号 ${createdUsername} 注册成功，请继续登录。`
    ElMessage.success('注册成功，请继续登录')
    activeTab.value = 'login'
    emit('tab-change', 'login')
  } catch (error) {
    console.error('Register request failed', error)
    registerError.value = resolveAuthErrorMessage(error, 'register')
  } finally {
    registerLoading.value = false
  }
}

function resolveAuthErrorMessage(error, mode) {
  const status = error?.response?.status
  const detail = error?.response?.data?.detail

  if (!error?.response) {
    return '认证服务不可用，请确认后端已启动，并检查 /api/health 是否可访问。'
  }

  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  if (mode === 'login' && status === 401) {
    return '用户名或密码错误，请重新输入。'
  }

  if (mode === 'register' && (status === 400 || status === 409)) {
    return '该账号已存在，请更换用户名后重试。'
  }

  if (status >= 500) {
    return '认证服务当前不可用，请稍后再试。'
  }

  return mode === 'login' ? '登录失败，请稍后再试。' : '注册失败，请稍后再试。'
}
</script>

<style scoped>
.auth-card {
  position: relative;
  padding: 42px 38px 36px;
  background: #f7f8f4;
  color: #17201d;
}

.auth-close {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 34px;
  height: 34px;
  border: 1px solid #c6ccc5;
  background: #eef0eb;
  color: #5f6b64;
  cursor: pointer;
}

.auth-card-head {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 14px;
  align-items: start;
}

.auth-badge {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #17201d;
  color: #b5f04c;
  font: 800 0.68rem ui-monospace, monospace;
}

.auth-kicker {
  color: #68766d;
  font: 700 0.65rem ui-monospace, monospace;
  text-transform: uppercase;
  letter-spacing: 0;
}

.auth-card-head h2 {
  margin-top: 8px;
  font-size: 1.48rem;
  letter-spacing: 0;
}

.auth-card-head p {
  margin-top: 10px;
  max-width: 46ch;
  color: #66726b;
  line-height: 1.72;
  font-size: 0.82rem;
  text-wrap: pretty;
}

.form-success,
.form-error {
  margin-top: 16px;
  padding: 11px 12px;
  font-size: 0.82rem;
  line-height: 1.6;
}

.form-success {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #9bb788;
  background: #e7efe1;
  color: #39562b;
}

.form-error {
  border: 1px solid #d9a38f;
  background: #f6e7e1;
  color: #7f3e2b;
}

.auth-tabs {
  margin-top: 28px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border: 1px solid #c8cec6;
}

.auth-tabs button {
  height: 42px;
  border: 0;
  border-right: 1px solid #c8cec6;
  background: #eef0eb;
  color: #68746d;
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease;
}

.auth-tabs button:last-child {
  border-right: 0;
}

.auth-tabs button.active {
  background: #17201d;
  color: #b5f04c;
}

.auth-tabs button:focus-visible,
.auth-close:focus-visible,
.auth-submit:focus-visible,
.switch-link:focus-visible {
  outline: 2px solid #6f914f;
  outline-offset: 3px;
}

.auth-form {
  margin-top: 22px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.auth-fade-enter-active,
.auth-fade-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.auth-fade-enter-from,
.auth-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

.field-label {
  color: #526058;
  font-size: 0.76rem;
  font-weight: 600;
}

.form-field {
  min-height: 50px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid #c8cec6;
  background: #fff;
  color: #6f914f;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.form-field:focus-within {
  border-color: #6f914f;
  box-shadow: 0 0 0 3px rgba(111, 145, 79, 0.12);
}

.form-field input {
  min-width: 0;
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: #17201d;
  font-size: 0.92rem;
}

.form-field input::placeholder {
  color: #9aa39d;
}

.auth-submit {
  margin-top: 8px;
  min-height: 48px;
  border: 1px solid #17201d;
  background: #17201d;
  color: #f4f6f1;
  font-size: 0.86rem;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease;
}

.auth-submit:hover:not(:disabled) {
  background: #26332d;
  transform: translateY(-1px);
}

.auth-submit:active:not(:disabled) {
  transform: translateY(1px);
}

.auth-submit:disabled {
  opacity: 0.7;
  cursor: default;
}

.loading-icon {
  animation: spin 1s linear infinite;
}

.auth-helper {
  margin-top: 20px;
  padding: 15px 16px;
  border-left: 3px solid #6f914f;
  background: #ecefe9;
}

.auth-helper strong {
  color: #26322c;
  font-size: 0.8rem;
}

.auth-helper p {
  margin-top: 8px;
  color: #69756e;
  font-size: 0.76rem;
  line-height: 1.72;
}

.auth-switch {
  margin-top: 18px;
  color: #6d7871;
  font-size: 0.78rem;
  text-align: center;
}

.switch-link {
  margin-left: 6px;
  padding: 0;
  border: none;
  background: transparent;
  color: #527634;
  cursor: pointer;
  font: 700 inherit;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 720px) {
  .auth-card {
    padding: 32px 24px 30px;
  }

  .auth-card-head {
    grid-template-columns: 38px 1fr;
    gap: 12px;
  }

  .auth-badge {
    width: 38px;
    height: 38px;
  }

  .auth-card-head h2 {
    font-size: 1.28rem;
  }
}
</style>

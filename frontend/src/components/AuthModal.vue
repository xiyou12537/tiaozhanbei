<template>
  <teleport to="body">
    <transition name="modal-fade">
      <div class="auth-overlay" v-if="visible" @click.self="closeModal">
        <div class="auth-dialog">
          <!-- 关闭按钮 -->
          <button class="auth-close" @click="closeModal">
            <el-icon :size="20"><Close /></el-icon>
          </button>

          <!-- 装饰 -->
          <div class="auth-decor">
            <div class="decor-ring"></div>
            <div class="decor-core"></div>
          </div>

          <!-- Tab 切换 -->
          <div class="auth-tabs">
            <button
              :class="{ active: activeTab === 'login' }"
              @click="switchTab('login')"
            >登录</button>
            <button
              :class="{ active: activeTab === 'register' }"
              @click="switchTab('register')"
            >注册</button>
          </div>

          <!-- 登录表单 -->
          <form v-if="activeTab === 'login'" @submit.prevent="handleLogin" class="auth-form">
            <div class="form-field">
              <el-icon :size="18"><User /></el-icon>
              <input
                v-model="loginForm.username"
                type="text"
                placeholder="用户名"
                autocomplete="username"
                ref="loginUserInput"
              />
            </div>
            <div class="form-field">
              <el-icon :size="18"><Lock /></el-icon>
              <input
                v-model="loginForm.password"
                type="password"
                placeholder="密码"
                autocomplete="current-password"
              />
            </div>
            <div class="form-error" v-if="loginError">{{ loginError }}</div>
            <button type="submit" class="auth-submit" :disabled="loginLoading">
              <span v-if="!loginLoading">登 录</span>
              <el-icon v-else :size="20" class="loading-icon"><Loading /></el-icon>
            </button>
          </form>

          <!-- 注册表单 -->
          <form v-if="activeTab === 'register'" @submit.prevent="handleRegister" class="auth-form">
            <div class="form-field">
              <el-icon :size="18"><User /></el-icon>
              <input
                v-model="registerForm.username"
                type="text"
                placeholder="用户名"
                autocomplete="username"
                ref="regUserInput"
              />
            </div>
            <div class="form-field">
              <el-icon :size="18"><Lock /></el-icon>
              <input
                v-model="registerForm.password"
                type="password"
                placeholder="密码（至少6位）"
                autocomplete="new-password"
              />
            </div>
            <div class="form-field">
              <el-icon :size="18"><Lock /></el-icon>
              <input
                v-model="registerForm.confirm"
                type="password"
                placeholder="确认密码"
                autocomplete="new-password"
              />
            </div>
            <div class="form-error" v-if="registerError">{{ registerError }}</div>
            <button type="submit" class="auth-submit" :disabled="registerLoading">
              <span v-if="!registerLoading">注 册</span>
              <el-icon v-else :size="20" class="loading-icon"><Loading /></el-icon>
            </button>
          </form>

          <p class="auth-switch">
            <template v-if="activeTab === 'login'">
              还没有账号？<a @click="switchTab('register')">立即注册</a>
            </template>
            <template v-else>
              已有账号？<a @click="switchTab('login')">返回登录</a>
            </template>
          </p>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { ref, reactive, watch, nextTick } from 'vue'
import { login, register } from '../api'

const props = defineProps({
  visible: { type: Boolean, default: false },
  initialTab: { type: String, default: 'login' },
})
const emit = defineEmits(['close', 'success'])

// ── 当前 tab ──
const activeTab = ref(props.initialTab)
watch(() => props.initialTab, (val) => { activeTab.value = val })
watch(() => props.visible, (val) => {
  if (val) {
    activeTab.value = props.initialTab
    loginError.value = ''
    registerError.value = ''
    // 自动聚焦
    nextTick(() => {
      if (activeTab.value === 'login') loginUserInput.value?.focus()
      else regUserInput.value?.focus()
    })
  }
})

function switchTab(tab) {
  activeTab.value = tab
  loginError.value = ''
  registerError.value = ''
}

// ── 登录 ──
const loginUserInput = ref(null)
const loginForm = reactive({ username: '', password: '' })
const loginLoading = ref(false)
const loginError = ref('')

async function handleLogin() {
  loginError.value = ''
  if (!loginForm.username.trim()) { loginError.value = '请输入用户名'; return }
  if (!loginForm.password) { loginError.value = '请输入密码'; return }

  loginLoading.value = true
  try {
    const { data } = await login(loginForm.username, loginForm.password)
    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify({ id: data.user_id, username: data.username }))
    loginForm.username = ''
    loginForm.password = ''
    emit('success')
    closeModal()
  } catch (e) {
    loginError.value = e.response?.data?.detail || '登录失败，请检查用户名和密码'
  } finally {
    loginLoading.value = false
  }
}

// ── 注册 ──
const regUserInput = ref(null)
const registerForm = reactive({ username: '', password: '', confirm: '' })
const registerLoading = ref(false)
const registerError = ref('')

async function handleRegister() {
  registerError.value = ''
  if (!registerForm.username.trim()) { registerError.value = '请输入用户名'; return }
  if (!registerForm.password) { registerError.value = '请输入密码'; return }
  if (registerForm.password.length < 6) { registerError.value = '密码至少6位'; return }
  if (registerForm.password !== registerForm.confirm) { registerError.value = '两次密码不一致'; return }

  registerLoading.value = true
  try {
    const { data } = await register(registerForm.username, registerForm.password)
    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify({ id: data.user_id, username: data.username }))
    registerForm.username = ''
    registerForm.password = ''
    registerForm.confirm = ''
    emit('success')
    closeModal()
  } catch (e) {
    registerError.value = e.response?.data?.detail || '注册失败，请稍后重试'
  } finally {
    registerLoading.value = false
  }
}

function closeModal() {
  emit('close')
}
</script>

<style scoped>
/* ===== Overlay ===== */
.auth-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ===== Dialog ===== */
.auth-dialog {
  position: relative;
  width: 420px;
  background: linear-gradient(160deg, #141e2b 0%, #0f1923 100%);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 40px 36px 32px;
  box-shadow: 0 32px 80px rgba(0, 0, 0, 0.5);
}

.auth-close {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: rgba(255, 255, 255, 0.03);
  color: #5a6d80;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.auth-close:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #c0ccda;
}

/* ===== 装饰 ===== */
.auth-decor {
  position: absolute;
  top: -30px;
  left: 50%;
  transform: translateX(-50%);
  width: 60px;
  height: 60px;
  pointer-events: none;
}
.decor-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1.5px solid rgba(54, 207, 201, 0.25);
  animation: decor-spin 6s linear infinite;
}
.decor-ring::before {
  content: '';
  position: absolute;
  top: -3px;
  left: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #36cfc9;
  transform: translateX(-50%);
}
.decor-core {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(54, 207, 201, 0.3);
  box-shadow: 0 0 20px rgba(54, 207, 201, 0.2);
}
@keyframes decor-spin {
  to { transform: rotate(360deg); }
}

/* ===== Tabs ===== */
.auth-tabs {
  display: flex;
  gap: 4px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 10px;
  padding: 4px;
  margin-bottom: 28px;
}
.auth-tabs button {
  flex: 1;
  padding: 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #5a6d80;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s;
}
.auth-tabs button.active {
  background: rgba(54, 207, 201, 0.12);
  color: #36cfc9;
}

/* ===== Form ===== */
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-field {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  height: 46px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  transition: border-color 0.2s;
  color: #5a6d80;
}
.form-field:focus-within {
  border-color: rgba(54, 207, 201, 0.3);
}
.form-field input {
  flex: 1;
  border: none;
  background: transparent;
  color: #e8eaed;
  font-size: 0.9rem;
  outline: none;
}
.form-field input::placeholder {
  color: #4a5d70;
}

.form-error {
  font-size: 0.8rem;
  color: #ff4d4f;
  padding: 0 4px;
}

.auth-submit {
  height: 46px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #36cfc9, #08979c);
  color: #fff;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.15s;
  margin-top: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.auth-submit:hover:not(:disabled) {
  opacity: 0.92;
  transform: translateY(-1px);
}
.auth-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-icon {
  animation: spin-icon 0.8s linear infinite;
}
@keyframes spin-icon {
  to { transform: rotate(360deg); }
}

/* ===== Switch ===== */
.auth-switch {
  text-align: center;
  margin-top: 20px;
  font-size: 0.82rem;
  color: #5a6d80;
}
.auth-switch a {
  color: #36cfc9;
  cursor: pointer;
  text-decoration: none;
  font-weight: 500;
}
.auth-switch a:hover {
  text-decoration: underline;
}

/* ===== Transition ===== */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.25s ease;
}
.modal-fade-enter-active .auth-dialog,
.modal-fade-leave-active .auth-dialog {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
.modal-fade-enter-from .auth-dialog {
  transform: translateY(20px) scale(0.97);
  opacity: 0;
}
.modal-fade-leave-to .auth-dialog {
  transform: translateY(-10px) scale(0.98);
  opacity: 0;
}
</style>

<template>
  <div class="auth-container">
    <div class="auth-card">
      <h1>量子线路划分优化系统</h1>
      <p class="subtitle">分布式量子计算 — 量子比特分区与芯片拓扑映射</p>
      <el-form :model="form" :rules="rules" ref="formRef" size="large">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleLogin" :loading="loading" style="width:100%">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <p class="footer-text">还没有账号？<router-link to="/register">立即注册</router-link></p>
      <p class="footer-text"><router-link to="/">← 返回首页</router-link></p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api'

const router = useRouter()
const loading = ref(false)
const formRef = ref(null)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const { data } = await login(form.username, form.password)
    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify({ id: data.user_id, username: data.username }))
    ElMessage.success('登录成功')
    router.push('/app')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-container { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); }
.auth-card { width: 420px; background: #fff; border-radius: 12px; padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,.3); }
.auth-card h1 { text-align: center; font-size: 1.4rem; color: #1a1a2e; margin-bottom: 6px; }
.subtitle { text-align: center; font-size: 0.8rem; color: #999; margin-bottom: 28px; }
.footer-text { text-align: center; font-size: 0.85rem; color: #999; margin-top: 8px; }
.footer-text a { color: #409eff; }
</style>

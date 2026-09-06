<template>
  <div class="auth-page">
    <div class="panel">
      <div class="brand"><span class="mark" />聊天知识库系统</div>
      <div class="sub">登录 · 本地运行 · 数据不出本机</div>
      <a-form layout="vertical">
        <a-form-item label="用户名">
          <a-input v-model:value="username" placeholder="admin" size="large" @pressEnter="doLogin" />
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model:value="password" placeholder="密码" size="large" @pressEnter="doLogin" />
        </a-form-item>
        <a-button type="primary" size="large" block :loading="loading" @click="doLogin">登 录</a-button>
      </a-form>
      <div class="foot">
        默认账号 admin / admin123 ·
        <router-link to="/register">注册新账号</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)

async function doLogin() {
  if (!username.value || !password.value) return message.warning('请输入用户名和密码')
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    router.push('/dashboard')
  } catch { /* 拦截器已提示 */ } finally {
    loading.value = false
  }
}
</script>

<style lang="less" scoped>
@import '../styles/variables.less';

.auth-page {
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  background: @bg;
  // 细点阵网格：工具感，替代 AI 味渐变
  background-image: radial-gradient(circle, #e0e4e9 1px, transparent 1px);
  background-size: 22px 22px;
}
.panel {
  width: 372px;
  background: @panel;
  border: 1px solid @border;
  border-radius: @radius-lg;
  padding: 34px 32px 26px;
  border-top: 3px solid @green;
}
.brand { font-size: 18px; font-weight: 700; color: @text-1; display: flex; align-items: center; gap: 8px;
  .mark { width: 12px; height: 12px; background: @green; border-radius: 2px; } }
.sub { color: @text-3; font-size: 12px; margin: 6px 0 22px; }
.foot { text-align: center; color: @text-3; font-size: 12px; margin-top: 18px;
  a { color: @green-dark; } }
</style>

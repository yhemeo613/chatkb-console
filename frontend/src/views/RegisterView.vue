<template>
  <div class="auth-page">
    <div class="panel">
      <div class="brand"><span class="mark" />注册账号</div>
      <div class="sub">注册即开通「普通用户」权限，可用语义搜索与对话回复</div>
      <a-form layout="vertical">
        <a-form-item label="用户名（至少 3 个字符）">
          <a-input v-model:value="form.username" placeholder="字母或数字" @pressEnter="doRegister" />
        </a-form-item>
        <a-form-item label="昵称（可选）">
          <a-input v-model:value="form.nickname" placeholder="怎么称呼你" @pressEnter="doRegister" />
        </a-form-item>
        <a-form-item label="密码（至少 6 位）">
          <a-input-password v-model:value="form.password" @pressEnter="doRegister" />
        </a-form-item>
        <a-form-item label="确认密码">
          <a-input-password v-model:value="form.password2" @pressEnter="doRegister" />
        </a-form-item>
        <a-button type="primary" size="large" block :loading="loading" @click="doRegister">注 册</a-button>
        <div class="foot"><router-link to="/login">已有账号？去登录</router-link></div>
      </a-form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', nickname: '', password: '', password2: '' })

async function doRegister() {
  if (form.username.trim().length < 3) return message.warning('用户名至少 3 个字符')
  if (form.password.length < 6) return message.warning('密码至少 6 位')
  if (form.password !== form.password2) return message.warning('两次输入的密码不一致')
  loading.value = true
  try {
    await auth.register({ username: form.username.trim(), nickname: form.nickname.trim(), password: form.password })
    message.success('注册成功，已自动登录')
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
  background-image: radial-gradient(circle, #e0e4e9 1px, transparent 1px);
  background-size: 22px 22px;
}
.panel {
  width: 400px;
  background: @panel;
  border: 1px solid @border;
  border-radius: @radius-lg;
  border-top: 3px solid @green;
  padding: 34px 32px 26px;
}
.brand { font-size: 18px; font-weight: 700; color: @text-1; display: flex; align-items: center; gap: 8px;
  .mark { width: 12px; height: 12px; background: @green; border-radius: 2px; } }
.sub { color: @text-3; font-size: 12px; margin: 6px 0 22px; }
.foot { text-align: center; color: @text-3; font-size: 12px; margin-top: 18px;
  a { color: @green-dark; } }
</style>

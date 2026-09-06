<template>
  <a-layout style="height: 100vh; overflow: hidden">
    <a-layout-sider v-model:collapsed="collapsed" theme="light" :width="208" class="sidebar" collapsible>
      <div class="logo">
        <span class="mark" />
        <span v-if="!collapsed" class="logo-text">聊天知识库<em>CONSOLE</em></span>
      </div>
      <sidebar-menu :items="auth.menus" />
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="header">
        <span class="title">{{ route.name || '工作台' }}</span>
        <span class="right">
          <span class="service" :class="{ down: !system.ollama_up }">Ollama</span>
          <span class="service" :class="system.redis_backend === 'redis' ? '' : 'warn'">Redis</span>
          <a-divider type="vertical" />
          <a-dropdown>
            <span class="user">
              {{ auth.user?.nickname || auth.user?.username || '用户' }}
              <a-tag v-if="auth.user?.is_superuser" color="green" style="margin-left: 2px">超管</a-tag>
              <DownOutlined style="font-size: 10px; color: #9aa4b0" />
            </span>
            <template #overlay>
              <a-menu>
                <a-menu-item key="pwd" @click="pwdOpen = true"><KeyOutlined /> 修改密码</a-menu-item>
                <a-menu-item key="out" @click="logout"><LogoutOutlined /> 退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </span>
      </a-layout-header>
      <a-layout-content class="content">
        <router-view />
      </a-layout-content>
      <a-layout-footer class="footer">
        聊天知识库系统 · 本地运行 · FastAPI + Vue3 + RBAC + Redis + Chroma + Ollama
      </a-layout-footer>
    </a-layout>

    <a-modal v-model:open="pwdOpen" title="修改密码" @ok="changePwd" :confirm-loading="pwdSaving">
      <a-form layout="vertical">
        <a-form-item label="旧密码" required><a-input-password v-model:value="pwd.old" /></a-form-item>
        <a-form-item label="新密码（至少 6 位）" required><a-input-password v-model:value="pwd.new1" /></a-form-item>
        <a-form-item label="确认新密码" required><a-input-password v-model:value="pwd.new2" /></a-form-item>
      </a-form>
    </a-modal>
  </a-layout>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DownOutlined, KeyOutlined, LogoutOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../api'
import { useAuthStore } from '../stores/auth'
import SidebarMenu from '../components/SidebarMenu.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = ref(false)
const system = reactive({ ollama_up: true, redis_backend: '' })
const pwdOpen = ref(false)
const pwdSaving = ref(false)
const pwd = reactive({ old: '', new1: '', new2: '' })

async function ping() {
  try {
    const d = await http.get('/system/dashboard')
    system.ollama_up = d.ollama_up
    system.redis_backend = d.redis_backend
  } catch { /* 拦截器已处理 */ }
}
if (auth.isLoggedIn) {
  ping()
  setInterval(ping, 15000)
}

function logout() {
  auth.logout()
  router.push('/login')
}

async function changePwd() {
  if (!pwd.old || !pwd.new1) return message.warning('请填写完整')
  if (pwd.new1.length < 6) return message.warning('新密码至少 6 位')
  if (pwd.new1 !== pwd.new2) return message.warning('两次输入的新密码不一致')
  pwdSaving.value = true
  try {
    await auth.changePassword(pwd.old, pwd.new1)
    message.success('密码已修改')
    pwdOpen.value = false
    pwd.old = pwd.new1 = pwd.new2 = ''
  } finally {
    pwdSaving.value = false
  }
}
</script>

<style lang="less" scoped>
@import '../styles/variables.less';

.sidebar {
  border-right: 1px solid @border;
  height: 100vh;

  :deep(.ant-layout-sider-children) {
    height: calc(100% - 48px);   // 底部留折叠触发器
    overflow-y: auto;
    overflow-x: hidden;
  }

  :deep(.logo) {
    height: @header-h;
    display: flex; align-items: center; gap: 8px;
    padding: 0 16px;
    font-weight: 700; font-size: 15px; color: @text-1;
    border-bottom: 1px solid @border;

    .mark { width: 10px; height: 10px; background: @green; border-radius: 2px; flex-shrink: 0; }
    .logo-text {
      display: flex; flex-direction: column; line-height: 1.15;
      em { font-style: normal; font-family: @display-font; font-size: 9px;
           letter-spacing: 0.28em; color: @text-3; font-weight: 400; }
    }
  }

  // 菜单：直角、满宽、选中 = 左侧绿条 + 淡绿底（拒绝圆角胶囊菜单）
  :deep(.ant-menu) {
    border-inline-end: none !important;
    padding-top: 6px;
  }
  :deep(.ant-menu-item),
  :deep(.ant-menu-submenu-title) {
    border-radius: 0;
    margin-inline: 0 !important;
    width: 100%;
    color: @text-2;
  }
  :deep(.ant-menu-item-selected) {
    background: @green-bg;
    color: @green-dark;
    box-shadow: inset 3px 0 0 @green;
    font-weight: 600;
  }
  :deep(.ant-menu-sub.ant-menu-inline) { background: #fbfcfd !important; }
  :deep(.ant-menu-submenu-selected > .ant-menu-submenu-title) { color: @green-dark; }
}

.header {
  height: @header-h; line-height: normal; flex-shrink: 0;
  background: @panel;
  border-bottom: 1px solid @border;
  box-shadow: none;
  padding: 0 20px;
  display: flex; align-items: center; justify-content: space-between;

  .title { font-size: 15px; font-weight: 700; color: @text-1; }
  .right { display: flex; align-items: center; gap: 10px; }

  // 服务名即状态：文字本身着色，去掉徽章装饰
  .service {
    font-size: 12px; color: @ok; background: @green-bg;
    padding: 2px 8px; border-radius: 3px;
    &.down { color: @danger; background: #fdf1f0; }
    &.warn { color: @warn; background: #fff7ec; }
  }
  .user { cursor: pointer; font-size: 13px; color: @text-1; display: inline-flex; align-items: center; gap: 4px; }
}

.content {
  margin: 14px 16px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;            // 唯一滚动区
  overflow-x: hidden;
}

.footer {
  background: @panel; border-top: 1px solid @border; color: @text-3;
  font-size: 12px; text-align: center; padding: 0; line-height: 36px; height: 36px; flex-shrink: 0;
}
</style>

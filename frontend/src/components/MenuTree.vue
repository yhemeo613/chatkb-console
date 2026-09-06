<template>
  <template v-for="m in items" :key="m.id">
    <a-sub-menu v-if="m.children && m.children.length" :key="m.id">
      <template #title>
        <component :is="iconComp(m.icon)" v-if="m.icon" />
        <span>{{ m.name }}</span>
      </template>
      <menu-tree :items="m.children" />
    </a-sub-menu>
    <a-menu-item v-else :key="m.path || m.id">
      <component :is="iconComp(m.icon)" v-if="m.icon" />
      <span>{{ m.name }}</span>
    </a-menu-item>
  </template>
</template>

<script setup>
import {
  ApiOutlined, AppstoreOutlined, ClockCircleOutlined, DashboardOutlined, DatabaseOutlined,
  FileTextOutlined, FundOutlined, MessageOutlined, ProfileOutlined,
  SafetyOutlined, SearchOutlined, SettingOutlined, TeamOutlined, UserOutlined,
} from '@ant-design/icons-vue'

defineOptions({ name: 'MenuTree' })
defineProps({ items: { type: Array, default: () => [] } })

const ICONS = {
  dashboard: DashboardOutlined,
  database: DatabaseOutlined,
  search: SearchOutlined,
  message: MessageOutlined,
  profile: ProfileOutlined,
  setting: SettingOutlined,
  safety: SafetyOutlined,
  user: UserOutlined,
  team: TeamOutlined,
  appstore: AppstoreOutlined,
  monitor: FundOutlined,
  task: ClockCircleOutlined,
  log: FileTextOutlined,
  api: ApiOutlined,
}
const iconComp = (name) => ICONS[name]
</script>

<template>
  <a-menu v-model:selectedKeys="selectedKeys" v-model:openKeys="openKeys" mode="inline" theme="light" @click="onMenu">
    <menu-tree :items="items" />
  </a-menu>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MenuTree from './MenuTree.vue'

const route = useRoute()
const router = useRouter()
const props = defineProps({ items: { type: Array, default: () => [] } })

const selectedKeys = ref([route.path])
const openKeys = ref([])

// 默认展开当前路由的祖先目录
watch(() => route.path, (p) => {
  selectedKeys.value = [p]
  const keys = []
  const walk = (nodes, parents) => {
    for (const n of nodes) {
      if (n.path === p) { keys.push(...parents); return true }
      if (n.children && walk(n.children, [...parents, n.id])) return true
    }
    return false
  }
  walk(props.items, [])
  openKeys.value = [...new Set([...openKeys.value, ...keys])]
}, { immediate: true })

const onMenu = ({ key }) => {
  if (typeof key === 'string' && key.startsWith('/')) router.push(key)
}
</script>

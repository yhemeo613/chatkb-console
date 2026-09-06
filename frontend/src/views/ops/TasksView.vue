<template>
  <a-card title="任务中心（入库 / 重建索引 / 档案同步）">
    <template #extra>
      <a-button @click="load"><ReloadOutlined /> 刷新</a-button>
    </template>

    <a-table :data-source="items" :loading="loading" row-key="id" :pagination="false" size="middle">
      <a-table-column title="任务" data-index="name" :width="220" />
      <a-table-column title="状态" :width="100">
        <template #default="{ record }">
          <a-tag :color="statusColor(record.status)">{{ statusText(record.status) }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="进度" :width="180">
        <template #default="{ record }">
          <a-progress :percent="record.total ? Math.round((record.done / record.total) * 100) : 0"
                      :status="record.status === 'failed' ? 'exception' : record.status === 'running' ? 'active' : 'normal'"
                      size="small" />
        </template>
      </a-table-column>
      <a-table-column title="最后消息" data-index="message" ellipsis />
      <a-table-column title="开始时间" :width="150">
        <template #default="{ record }">{{ fmtTime(record.created_at) }}</template>
      </a-table-column>
      <a-table-column title="耗时" :width="90">
        <template #default="{ record }">{{ dur(record) }}</template>
      </a-table-column>
    </a-table>
  </a-card>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import http from '../../api'
import { fmtTime } from '../../utils/format'

const items = ref([])
const loading = ref(false)
let timer = null

const statusColor = (s) => ({ success: 'success', running: 'processing', failed: 'error' }[s] || 'default')
const statusText = (s) => ({ success: '成功', running: '进行中', failed: '失败' }[s] || s)
const dur = (r) => r.finished_at ? `${Math.round(r.finished_at - r.created_at)}s` : '—'

async function load() {
  loading.value = true
  try {
    items.value = await http.get('/ops/tasks', { params: { limit: 50 } })
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

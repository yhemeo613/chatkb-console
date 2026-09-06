<template>
  <a-card title="操作日志（写操作审计）">
    <template #extra>
      <a-button @click="load()"><ReloadOutlined /> 刷新</a-button>
    </template>

    <a-table :data-source="items" :loading="loading" row-key="id" size="middle" :pagination="pagination" @change="onPage">
      <a-table-column title="时间" :width="160">
        <template #default="{ record }">{{ fmtTime(record.created_at) }}</template>
      </a-table-column>
      <a-table-column title="操作人" data-index="username" :width="120" />
      <a-table-column title="方法" :width="90">
        <template #default="{ record }">
          <a-tag :color="{ POST: 'blue', PUT: 'orange', DELETE: 'red' }[record.method] || 'default'">{{ record.method }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="接口" data-index="path" ellipsis />
      <a-table-column title="结果" :width="90">
        <template #default="{ record }">
          <a-tag :color="record.status_code < 400 ? 'success' : 'error'">{{ record.status_code }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="来源 IP" data-index="ip" :width="130" />
      <a-table-column title="耗时" :width="90">
        <template #default="{ record }">{{ record.duration_ms }} ms</template>
      </a-table-column>
    </a-table>
  </a-card>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import http from '../../api'
import { fmtTime } from '../../utils/format'

const items = ref([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)

const pagination = computed(() => ({
  current: page.value, total: total.value, pageSize: 20, showTotal: (t) => `共 ${t} 条`,
}))

async function load(p = page.value) {
  loading.value = true
  try {
    const d = await http.get('/ops/logs', { params: { page: p, size: 20 } })
    items.value = d.items
    total.value = d.total
    page.value = p
  } finally {
    loading.value = false
  }
}
const onPage = (pg) => load(pg.current)
onMounted(() => load(1))
</script>

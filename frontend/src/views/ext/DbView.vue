<template>
  <a-row :gutter="16">
    <a-col :span="7">
      <a-card title="数据表（SQLite · 只读）" size="small">
        <a-list :data-source="tables" size="small" style="max-height: 560px; overflow: auto">
          <template #renderItem="{ item }">
            <a-list-item style="cursor: pointer" :class="{ active: item.name === current }" @click="openTable(item)">
              <a-list-item-meta>
                <template #title>{{ item.name }}</template>
                <template #description>{{ item.rows }} 行 · {{ item.columns.length }} 列</template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </a-col>
    <a-col :span="17">
      <a-card :title="current ? `表：${current}（${total} 行）` : '选择左侧表浏览数据'" size="small" style="margin-bottom: 16px">
        <a-table v-if="current" :data-source="rows" :columns="cols" row-key="_rk" size="small"
                 :pagination="{ total, pageSize: 20, current: page, showTotal: (t) => `共 ${t} 行` }" @change="onPage" />
        <a-empty v-else description="选择表查看前 20 行" />
      </a-card>
      <a-card title="只读 SQL 控制台（SELECT / PRAGMA / EXPLAIN）" size="small">
        <a-textarea v-model:value="sql" class="mono" :rows="4"
                    placeholder="SELECT model, COUNT(*) c FROM llm_usage GROUP BY model" />
        <a-button type="primary" style="margin-top: 8px" :loading="running" @click="run">执行查询</a-button>
        <div v-if="result" style="margin-top: 10px">
          <div class="page-tip">{{ result.row_count }} 行 · {{ result.ms }} ms</div>
          <pre class="mono" style="font-size: 12px; background: #fafbfc; padding: 10px; border-radius: 6px; max-height: 260px; overflow: auto">{{ tableText(result) }}</pre>
        </div>
      </a-card>
    </a-col>
  </a-row>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import http from '../../api'

const tables = ref([])
const current = ref('')
const rows = ref([])
const cols = ref([])
const total = ref(0)
const page = ref(1)
const sql = ref('')
const running = ref(false)
const result = ref(null)

async function load() { tables.value = await http.get('/ext/db/tables') }
async function openTable(item) {
  current.value = item.name; page.value = 1
  const d = await http.get('/ext/db/rows', { params: { table: item.name, page: 1, size: 20 } })
  rows.value = d.items.map((r, i) => ({ ...Object.fromEntries(d.columns.map((c, j) => [c, r[j]])), _rk: i }))
  cols.value = d.columns.map((c) => ({ title: c, dataIndex: c, key: c, ellipsis: true }))
  total.value = d.total
}
async function onPage(pg) {
  const d = await http.get('/ext/db/rows', { params: { table: current.value, page: pg.current, size: 20 } })
  rows.value = d.items.map((r, i) => ({ ...Object.fromEntries(d.columns.map((c, j) => [c, r[j]])), _rk: i }))
  page.value = pg.current
}
async function run() {
  if (!sql.value.trim()) return
  running.value = true
  try { result.value = await http.post('/ext/db/query', { sql: sql.value }) }
  finally { running.value = false }
}
const tableText = (r) => [r.columns.join(' | '), ...r.items.map((row) => row.join(' | '))].join('\n')

onMounted(load)
</script>

<style lang="less" scoped>
@import '../../styles/variables.less';
.active { background: @green-bg; }
</style>

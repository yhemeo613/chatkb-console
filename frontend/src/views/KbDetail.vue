<template>
  <div v-if="kb">
    <a-page-header :title="kb.name" :sub-title="kb.description" style="padding: 0 0 12px" @back="$router.push('/kbs')">
      <template #tags>
        <a-tag :color="kb.type === 'persona' ? 'orange' : 'blue'">{{ kb.type === 'persona' ? '个人档案' : '文档知识库' }}</a-tag>
      </template>
      <template #extra>
        <a-button :disabled="taskRunning" :loading="taskRunning" @click="rebuild">
          <ReloadOutlined /> 重建索引
        </a-button>
      </template>
    </a-page-header>

    <a-card v-if="kb.type === 'docs'" style="margin-bottom: 16px">
      <a-upload-dragger
        :show-upload-list="false" multiple
        :custom-request="upload" accept=".pdf,.epub,.docx,.txt,.md,.html,.htm"
      >
        <p class="ant-upload-drag-icon"><InboxOutlined /></p>
        <p class="ant-upload-text">点击或拖拽文件到这里上传</p>
        <p class="ant-upload-hint">支持 PDF / EPUB / DOCX / TXT / MD / HTML，上传后自动解析入库；扫描版 PDF 需要先 OCR</p>
      </a-upload-dragger>
      <a-progress v-if="taskRunning" :percent="taskPercent" status="active" style="margin-top: 12px" />
      <div v-if="taskLog.length" class="mono" style="font-size: 12px; color: #8a919f; max-height: 120px; overflow: auto; margin-top: 8px">
        <div v-for="(l, i) in taskLog" :key="i">{{ l }}</div>
      </div>
    </a-card>

    <a-card :title="`文档列表（${docs.length}）`">
      <a-table :data-source="docs" :pagination="false" row-key="id" size="middle">
        <a-table-column title="文件名" data-index="filename" />
        <a-table-column title="大小" :width="100">
          <template #default="{ record }">{{ fmtSize(record.size) }}</template>
        </a-table-column>
        <a-table-column title="状态" :width="100">
          <template #default="{ record }">
            <a-tooltip :title="record.error">
              <a-tag :color="statusColor(record.status)">{{ statusText(record.status) }}</a-tag>
            </a-tooltip>
          </template>
        </a-table-column>
        <a-table-column title="文本块" data-index="chunks" :width="80" />
        <a-table-column title="更新时间" :width="160">
          <template #default="{ record }">{{ fmtTime(record.updated_at) }}</template>
        </a-table-column>
        <a-table-column title="操作" :width="80">
          <template #default="{ record }">
            <a-popconfirm title="删除该文档及其索引？" @confirm="delDoc(record)">
              <a style="color: #ff4d4f">删除</a>
            </a-popconfirm>
          </template>
        </a-table-column>
      </a-table>
    </a-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { InboxOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../api'
import { fmtSize, fmtTime } from '../utils/format'

const route = useRoute()
const kbId = route.params.id
const kb = ref(null)
const docs = ref([])
const taskRunning = ref(false)
const taskPercent = ref(0)
const taskLog = ref([])
const wsRef = ref(null)
let pollTimer = null

const statusColor = (s) => ({ done: 'success', processing: 'processing', pending: 'default', failed: 'error' }[s] || 'default')
const statusText = (s) => ({ done: '已入库', processing: '处理中', pending: '待处理', failed: '失败' }[s] || s)

async function load() {
  kb.value = await http.get(`/kbs/${kbId}`)
  docs.value = await http.get(`/kbs/${kbId}/documents`)
}

function watchTask(taskId) {
  taskRunning.value = true
  taskLog.value = []
  taskPercent.value = 0
  let settled = false

  const finish = (err, msg) => {
    if (settled) return
    settled = true
    clearInterval(pollTimer)
    try { ws.value?.close() } catch { /* noop */ }
    taskRunning.value = false
    err ? message.error(`入库失败：${err}`) : message.success('入库完成')
    load()
  }

  // 优先 WebSocket 实时推送；失败自动回退轮询
  const startPolling = () => {
    if (settled) return
    pollTimer = setInterval(async () => {
      const t = await http.get(`/system/tasks/${taskId}`)
      taskPercent.value = t.total ? Math.round((t.done / t.total) * 100) : 0
      taskLog.value = t.log || []
      if (t.status !== 'running') finish(t.status === 'success' ? null : t.error)
    }, 1500)
  }

  try {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/tasks/${taskId}?token=${localStorage.getItem('chatkb_token')}`)
    wsRef.value = ws
    ws.onmessage = (ev) => {
      const t = JSON.parse(ev.data)
      taskPercent.value = t.total ? Math.round((t.done / t.total) * 100) : 0
      if (t.message && taskLog.value[taskLog.value.length - 1] !== t.message) taskLog.value.push(t.message)
      if (['success', 'failed'].includes(t.status)) finish(t.status === 'success' ? null : (t.error || t.message))
    }
    ws.onerror = startPolling
    ws.onclose = () => { if (!settled) startPolling() }
    // 兜底：15 秒还没连上就转轮询
    setTimeout(() => { if (!settled && ws.readyState !== 1) startPolling() }, 15000)
  } catch {
    startPolling()
  }
}

async function upload({ file, onSuccess }) {
  const fd = new FormData()
  fd.append('files', file)
  try {
    const res = await http.post(`/kbs/${kbId}/documents`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    onSuccess(res)
    watchTask(res.task_id)
    await load()
  } catch { /* 拦截器已提示 */ }
}

async function rebuild() {
  const res = await http.post(`/kbs/${kbId}/rebuild`)
  watchTask(res.task_id)
}

async function delDoc(doc) {
  await http.delete(`/kbs/${kbId}/documents/${doc.id}`)
  message.success('已删除')
  await load()
}

onMounted(async () => {
  await load()
  // 页面刷新时如有进行中的文档，自动恢复轮询
  if (docs.value.some((d) => ['pending', 'processing'].includes(d.status))) taskRunning.value = true
})
onUnmounted(() => { clearInterval(pollTimer); try { wsRef.value?.close() } catch { /* noop */ } })
</script>

<template>
  <div>
    <!-- 顶部状态带 -->
    <stat-strip :items="cards" />

    <!-- 服务详情 -->
    <a-row :gutter="16" style="margin-top: 16px">
      <a-col :span="8">
        <a-card title="Ollama 模型服务">
          <template #extra>
            <span class="status-chip" :class="d.ollama?.up ? 'ok' : 'bad'">{{ d.ollama?.up ? '在线' : '离线' }}</span>
          </template>
          <a-descriptions :column="1" size="small">
            <a-descriptions-item label="版本">{{ d.ollama?.version || '—' }}</a-descriptions-item>
            <a-descriptions-item label="服务地址">{{ d.ollama?.url }}</a-descriptions-item>
            <a-descriptions-item label="已装模型">
              <template v-if="d.ollama?.models?.length">
                <a-tag v-for="m in d.ollama.models" :key="m" color="blue" style="margin: 2px 4px 2px 0">{{ m }}</a-tag>
              </template>
              <span v-else style="color: #b4bac4">未安装</span>
            </a-descriptions-item>
            <a-descriptions-item label="用途">向量嵌入 + 回复生成（全本地）</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>

      <a-col :span="8">
        <a-card title="Redis 缓存">
          <template #extra>
            <span class="status-chip" :class="d.redis?.backend === 'redis' ? 'ok' : 'warn'">
              {{ d.redis?.backend === 'redis' ? '真连接' : '内存降级' }}
            </span>
          </template>
          <a-descriptions :column="1" size="small">
            <a-descriptions-item label="连接">{{ d.redis?.url }}</a-descriptions-item>
            <a-descriptions-item label="内存占用">{{ d.redis?.used_memory_human || '—' }}</a-descriptions-item>
            <a-descriptions-item label="业务键数量">{{ d.redis?.keys ?? '—' }}</a-descriptions-item>
            <a-descriptions-item label="用途">嵌入/搜索缓存 · 限流 · 任务状态 · 进度推送</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>

      <a-col :span="8">
        <a-card title="存储">
          <template #extra>
            <span class="status-chip ok">正常</span>
          </template>
          <a-descriptions :column="1" size="small">
            <a-descriptions-item label="SQLite 元数据">
              <a-tag style="margin-right: 6px">{{ fmtSize(d.sqlite?.size) }}</a-tag>
              {{ d.sqlite?.docs ?? 0 }} 篇文档 · {{ d.sqlite?.audit ?? 0 }} 条审计
            </a-descriptions-item>
            <a-descriptions-item label="Chroma 向量库">
              <a-tag>{{ fmtSize(d.chroma?.size) }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="文档上传目录">backend/data/uploads</a-descriptions-item>
            <a-descriptions-item label="个人档案目录">backend/data/personal</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>
    </a-row>

    <!-- 运行参数 -->
    <a-card title="运行参数" style="margin-top: 16px">
      <template #extra>
        <span style="color: #b4bac4; font-size: 12px">每 10 秒自动刷新</span>
      </template>
      <a-descriptions :column="4" size="small">
        <a-descriptions-item label="进程运行时长">{{ uptimeText }}</a-descriptions-item>
        <a-descriptions-item label="Python">{{ d.python }}</a-descriptions-item>
        <a-descriptions-item label="生成模型">{{ d.settings?.chat_model || '—' }}</a-descriptions-item>
        <a-descriptions-item label="向量模型">{{ d.settings?.embed_model || '—' }}</a-descriptions-item>
        <a-descriptions-item label="回复限流">{{ d.settings?.rate_limit_per_min ?? '—' }} 次/分钟</a-descriptions-item>
        <a-descriptions-item label="进行中任务">{{ d.task_running ?? 0 }}</a-descriptions-item>
        <a-descriptions-item label="登录账号">{{ auth.user?.username }}</a-descriptions-item>
        <a-descriptions-item label="部署形态">本机单机部署</a-descriptions-item>
      </a-descriptions>
    </a-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive } from 'vue'
import http from '../../api'
import { fmtSize } from '../../utils/format'
import { useAuthStore } from '../../stores/auth'
import StatStrip from '../../components/StatStrip.vue'

const d = reactive({})
const auth = useAuthStore()
let timer = null

const cards = computed(() => {
  const up = d.ollama?.up
  const redisOk = d.redis?.backend === 'redis'
  return [
    { label: '运行时长', value: uptimeText.value, sub: '本次进程' },
    { label: 'Ollama', value: up ? '在线' : '离线', tone: up ? 'ok' : 'bad', sub: `${d.ollama?.models?.length ?? 0} 个模型` },
    { label: 'Redis', value: redisOk ? '在线' : '降级', tone: redisOk ? 'ok' : 'warn', sub: d.redis?.used_memory_human || '' },
    { label: '进行中任务', value: d.task_running ?? 0, sub: '入库 / 重建索引' },
  ]
})

const uptimeText = computed(() => {
  const s = d.uptime_sec || 0
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h ? `${h} 时 ${m} 分` : `${m} 分 ${String(s % 60).padStart(2, '0')} 秒`
})

async function load() {
  Object.assign(d, await http.get('/ops/status'))
}
onMounted(() => {
  load()
  timer = setInterval(load, 10000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="dash">
    <!-- 统计带（数字滚动） -->
    <stat-strip :items="cards" class="rise" />

    <a-alert
      v-if="d.ollama_up === false"
      type="error" show-icon style="margin-top: 16px"
      message="Ollama 未启动"
      description="请先运行 ollama serve，否则嵌入和回复生成不可用。"
    />

    <!-- 趋势图 + 模型分布 -->
    <a-row :gutter="16" class="rise d1" style="margin-top: 16px">
      <a-col :span="16">
        <a-card title="Token 消耗趋势">
          <template #extra>
            <a-space>
              <a-radio-group v-if="auth.user?.is_superuser" v-model:value="scope" size="small" @change="loadUsage">
                <a-radio-button value="mine">我的</a-radio-button>
                <a-radio-button value="all">全系统</a-radio-button>
              </a-radio-group>
              <a-radio-group v-model:value="days" size="small" @change="loadUsage">
                <a-radio-button :value="1">今天</a-radio-button>
                <a-radio-button :value="7">7 天</a-radio-button>
                <a-radio-button :value="30">30 天</a-radio-button>
              </a-radio-group>
            </a-space>
          </template>
          <e-chart v-if="usage.by_day?.length" :option="trendOption" height="300px" />
          <a-empty v-else :image-style="{ height: '60px' }" style="padding: 60px 0"
                   description="还没有模型调用记录，去「对话回复」生成一次试试" />
        </a-card>
      </a-col>
      <a-col :span="8">
        <a-card title="模型分布（Tokens）">
          <e-chart v-if="usage.by_model?.length" :option="pieOption" height="300px" />
          <a-empty v-else :image-style="{ height: '60px' }" style="padding: 60px 0" description="暂无数据" />
        </a-card>
      </a-col>
    </a-row>

    <!-- 服务健康 + 最近文档 -->
    <a-row :gutter="16" class="rise d2" style="margin-top: 16px">
      <a-col :span="8">
        <a-card title="服务健康">
          <div class="health">
            <div class="h-row" v-for="h in health" :key="h.name">
              <span class="h-name">{{ h.name }}</span>
              <span class="status-chip" :class="h.cls">{{ h.value }}</span>
              <span class="h-sub">{{ h.sub }}</span>
            </div>
          </div>
          <div class="page-tip" style="margin-top: 10px">详细监控见「运维监控 → 服务状态」</div>
        </a-card>
      </a-col>
      <a-col :span="16">
        <a-card title="最近文档">
          <a-table :data-source="d.recent_docs || []" :pagination="false" row-key="id" size="small">
            <a-table-column title="文件" data-index="filename" />
            <a-table-column title="知识库" data-index="kb_name" :width="110" />
            <a-table-column title="状态" :width="90">
              <template #default="{ record }">
                <a-tag :color="statusColor(record.status)">{{ statusText(record.status) }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column title="块数" data-index="chunks" :width="70" />
            <a-table-column title="时间" :width="150">
              <template #default="{ record }">{{ fmtTime(record.updated_at) }}</template>
            </a-table-column>
          </a-table>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import http from '../api'
import { fmtTime } from '../utils/format'
import StatStrip from '../components/StatStrip.vue'
import EChart from '../components/charts/EChart.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const d = reactive({})
const settings = ref({})
const scope = ref(auth.user?.is_superuser ? 'all' : 'mine')
const days = ref(7)
const usage = reactive({})

// ---- 统计带数字滚动（700ms 缓出） ----
const anim = reactive({ kb: 0, docs: 0, done: 0, chunks: 0 })
function countUp(key, to) {
  const start = performance.now()
  const step = (t) => {
    const p = Math.min(1, (t - start) / 700)
    anim[key] = Math.round(to * (1 - Math.pow(1 - p, 3)))
    if (p < 1) requestAnimationFrame(step)
  }
  requestAnimationFrame(step)
}

const cards = computed(() => [
  { label: '知识库', value: anim.kb, sub: '个知识库' },
  { label: '文档总数', value: anim.docs, sub: '已上传' },
  { label: '已入库文档', value: anim.done, sub: d.doc_failed ? `${d.doc_failed} 个失败` : '全部成功' },
  { label: '文本块总数', value: anim.chunks, sub: '可检索片段' },
])

const fmtNum = (n) => {
  n = n || 0
  return n >= 10000 ? (n / 1000).toFixed(1) + 'k' : String(n)
}

async function loadUsage() {
  try {
    Object.assign(usage, await http.get('/llm/usage', { params: { days: days.value, scope: scope.value } }))
  } catch { /* 拦截器已提示 */ }
}

// ---- 图表配置（扁平工具风：细网格、绿主调、虚线次序列） ----
const trendOption = computed(() => ({
  animationDuration: 700,
  grid: { left: 52, right: 52, top: 40, bottom: 28 },
  tooltip: { trigger: 'axis' },
  legend: { data: ['Tokens', '调用次数'], top: 0, right: 0, textStyle: { color: '#5b6672' } },
  xAxis: { type: 'category', data: (usage.by_day || []).map((x) => x.day),
           axisLine: { lineStyle: { color: '#e3e7ec' } }, axisLabel: { color: '#98a2ae' } },
  yAxis: [
    { type: 'value', name: 'Tokens', splitLine: { lineStyle: { color: '#eef0f3' } },
      axisLabel: { color: '#98a2ae', formatter: (v) => (v >= 1000 ? v / 1000 + 'k' : v) } },
    { type: 'value', name: '次数', splitLine: { show: false }, axisLabel: { color: '#98a2ae' } },
  ],
  series: [
    { name: 'Tokens', type: 'line', smooth: true, data: (usage.by_day || []).map((x) => x.tokens),
      symbol: 'circle', symbolSize: 6,
      lineStyle: { width: 2.5, color: '#07c160' }, itemStyle: { color: '#07c160' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: 'rgba(7,193,96,0.22)' }, { offset: 1, color: 'rgba(7,193,96,0.02)' }] } } },
    { name: '调用次数', type: 'line', smooth: true, yAxisIndex: 1,
      data: (usage.by_day || []).map((x) => x.calls),
      symbol: 'circle', symbolSize: 6,
      lineStyle: { width: 2, color: '#5b6672', type: 'dashed' }, itemStyle: { color: '#5b6672' } },
  ],
}))

const DONUT_COLORS = ['#07c160', '#5ad8a6', '#aedccb', '#5b6672', '#98a2ae', '#c9ced6']
const pieOption = computed(() => ({
  animationDuration: 700,
  tooltip: { trigger: 'item', formatter: (p) => `${p.name}<br/>${fmtNum(p.value)} tokens（${p.percent}%）` },
  legend: { bottom: 0, textStyle: { color: '#5b6672', fontSize: 11 },
            formatter: (name) => (name.length > 16 ? name.slice(0, 16) + '…' : name) },
  series: [{
    type: 'pie', radius: ['48%', '70%'], center: ['50%', '44%'],
    itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
    label: { show: false },
    data: (usage.by_model || []).map((m, i) => ({
      name: m.model, value: m.tokens,
      itemStyle: { color: DONUT_COLORS[i % DONUT_COLORS.length] },
    })),
  }],
  graphic: [{
    type: 'text', left: 'center', top: '40%',
    style: { text: fmtNum(usage.summary?.total_tokens), fontSize: 22, fontWeight: 700,
             fontFamily: 'Bahnschrift', fill: '#1b2430', textAlign: 'center' },
  }, {
    type: 'text', left: 'center', top: '52%',
    style: { text: '总 Tokens', fontSize: 11, fill: '#98a2ae', textAlign: 'center' },
  }],
}))

const health = computed(() => [
  { name: 'Ollama', cls: d.ollama_up ? 'ok' : 'bad', value: d.ollama_up ? '在线' : '离线',
    sub: (d.models || []).length + ' 个模型' },
  { name: 'Redis', cls: d.redis_backend === 'redis' ? 'ok' : 'warn',
    value: d.redis_backend === 'redis' ? '在线' : '降级', sub: '缓存/限流/任务' },
  { name: '入库任务', cls: 'ok', value: String(d.task_running ?? 0), sub: '进行中' },
  { name: '失败文档', cls: d.doc_failed ? 'bad' : 'ok', value: String(d.doc_failed ?? 0),
    sub: '需重建索引' },
])

const statusColor = (s) => ({ done: 'success', processing: 'processing', pending: 'default', failed: 'error' }[s] || 'default')
const statusText = (s) => ({ done: '已入库', processing: '处理中', pending: '待处理', failed: '失败' }[s] || s)

onMounted(async () => {
  Object.assign(d, await http.get('/system/dashboard'))
  settings.value = await http.get('/system/settings')
  countUp('kb', d.kb_count || 0)
  countUp('docs', d.doc_total || 0)
  countUp('done', d.doc_done || 0)
  countUp('chunks', d.chunk_total || 0)
  loadUsage()
  setInterval(async () => Object.assign(d, await http.get('/system/dashboard')), 8000)
})
</script>

<style lang="less" scoped>
@import '../styles/variables.less';

.health {
  .h-row { display: flex; align-items: center; gap: 10px; padding: 7px 0;
    border-bottom: 1px dashed @border;
    &:last-child { border-bottom: none; } }
  .h-name { width: 80px; color: @text-2; font-size: 13px; }
  .h-sub { color: @text-3; font-size: 12px; margin-left: auto; }
}
</style>

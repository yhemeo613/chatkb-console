<template>
  <div>
    <a-tabs v-model:activeKey="tab">
      <!-- 服务商与模型 -->
      <a-tab-pane key="providers" tab="服务商与模型">
        <div style="margin-bottom: 14px">
          <a-button type="primary" @click="openCreate"><PlusOutlined /> 添加服务商</a-button>
          <span class="page-tip" style="margin-left: 12px">
            API Key 加密存储在本地数据库，仅本人可见；全部厂商走 OpenAI 兼容协议，一次配置即可用
          </span>
        </div>

        <!-- 本地 Ollama -->
        <a-card size="small" style="margin-bottom: 12px">
          <div class="prov-row">
            <div>
              <b>本地 Ollama</b>
              <a-tag color="green" style="margin-left: 8px">本地</a-tag>
              <div class="page-tip">{{ ollamaUrl }} /v1 · 无需 Key · 离线可用</div>
            </div>
            <a-button size="small" @click="load">刷新</a-button>
          </div>
        </a-card>

        <a-card v-for="p in providers" :key="p.id" size="small" style="margin-bottom: 12px"
                :style="p.builtin ? 'border-left: 3px solid #07c160' : ''">
          <div class="prov-row">
            <div>
              <b>{{ p.name }}</b>
              <a-tag v-if="p.builtin" color="green" style="margin-left: 8px">平台内置 · 全员可用</a-tag>
              <a-tag style="margin-left: 8px">{{ p.vendor_name }}</a-tag>
              <a-tag v-if="!p.enabled" color="orange">已停用</a-tag>
              <a-tag v-if="p.has_key" color="blue">已配 Key</a-tag>
              <div class="page-tip">{{ p.base_url }}</div>
              <div v-if="p.models?.length" class="page-tip" style="margin-top: 4px">
                模型（{{ p.models.length }}）：
                <a-tag v-for="m in p.models.slice(0, 8)" :key="m" style="margin: 2px 4px 2px 0">{{ m }}</a-tag>
                <span v-if="p.models.length > 8">…共 {{ p.models.length }} 个</span>
              </div>
              <div v-if="p.err" style="color: @danger; font-size: 12px">拉取失败：{{ p.err }}（可手动补模型）</div>
            </div>
            <a-space direction="vertical" size="4">
              <a-space>
                <a-button size="small" type="primary" ghost :loading="pulling === p.id" @click="pull(p)">拉取模型</a-button>
                <a-button size="small" :loading="testing === p.id" @click="test(p)">测试</a-button>
              </a-space>
              <a-space>
                <a @click="openEdit(p)">编辑</a>
                <a-popconfirm title="删除该服务商配置？" @confirm="del(p)">
                  <a style="color: #ff4d4f">删除</a>
                </a-popconfirm>
              </a-space>
            </a-space>
          </div>
        </a-card>

        <a-empty v-if="!providers.length" description="还没有云端服务商，点上方「添加服务商」接入 DeepSeek / Kimi / 智谱 / 通义 / 豆包 等" />
      </a-tab-pane>

      <!-- 用量统计 -->
      <a-tab-pane key="usage" tab="用量统计">
        <div style="margin-bottom: 12px">
          <a-radio-group v-model:value="days" @change="loadUsage">
            <a-radio-button :value="1">今天</a-radio-button>
            <a-radio-button :value="7">近 7 天</a-radio-button>
            <a-radio-button :value="30">近 30 天</a-radio-button>
          </a-radio-group>
        </div>

        <div class="stat-strip" style="margin-bottom: 16px">
          <div class="cell" v-for="c in usageCards" :key="c.label">
            <div class="label">{{ c.label }}</div>
            <div class="value">{{ c.value }}</div>
            <div class="sub">{{ c.sub }}</div>
          </div>
        </div>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-card title="按模型" size="small">
              <a-empty v-if="!usage.by_model?.length" description="暂无调用" />
              <div v-for="m in usage.by_model" :key="m.model" class="usage-row">
                <span class="usage-name">{{ m.model }}</span>
                <div class="usage-bar">
                  <div :style="{ width: barWidth(m.tokens) }" />
                </div>
                <span class="usage-val num">{{ m.calls }} 次 / {{ fmtNum(m.tokens) }} tok</span>
              </div>
            </a-card>
          </a-col>
          <a-col :span="12">
            <a-card title="按天调用" size="small">
              <a-empty v-if="!usage.by_day?.length" description="暂无调用" />
              <div v-for="d in usage.by_day" :key="d.day" class="usage-row">
                <span class="usage-name">{{ d.day }}</span>
                <div class="usage-bar">
                  <div :style="{ width: barWidth(d.calls, 'calls') }" />
                </div>
                <span class="usage-val num">{{ d.calls }} 次 / {{ fmtNum(d.tokens) }} tok</span>
              </div>
            </a-card>
          </a-col>
        </a-row>

        <a-card title="最近调用" size="small" style="margin-top: 16px">
          <a-table :data-source="usage.recent" row-key="id" size="small"
                   :pagination="{ total: usage.total, pageSize: 20, current: page, showTotal: (t) => `共 ${t} 条` }"
                   @change="onPage">
            <a-table-column title="时间" :width="150">
              <template #default="{ record }">{{ fmtTime(record.created_at) }}</template>
            </a-table-column>
            <a-table-column title="厂商" data-index="vendor" :width="100" />
            <a-table-column title="模型" data-index="model" ellipsis />
            <a-table-column title="类型" data-index="kind" :width="80" />
            <a-table-column title="Tokens" data-index="total_tokens" :width="90" />
            <a-table-column title="耗时" :width="90">
              <template #default="{ record }">{{ record.latency_ms }} ms</template>
            </a-table-column>
            <a-table-column title="结果" :width="70">
              <template #default="{ record }">
                <a-tag :color="record.ok ? 'success' : 'error'">{{ record.ok ? '成功' : '失败' }}</a-tag>
              </template>
            </a-table-column>
          </a-table>
        </a-card>
      </a-tab-pane>
    </a-tabs>

    <!-- 新建/编辑服务商 -->
    <a-modal v-model:open="editing" :title="form.id ? '编辑服务商' : '添加服务商'" @ok="save" :confirm-loading="saving" :width="560">
      <a-form layout="vertical">
        <a-form-item label="厂商" required>
          <a-select v-model:value="form.vendor" :options="presetOptions" :disabled="!!form.id"
                    @change="onVendorChange" placeholder="选择厂商" />
        </a-form-item>
        <a-form-item label="显示名" required><a-input v-model:value="form.name" placeholder="例：我的 DeepSeek" /></a-form-item>
        <a-form-item label="API Key" :extra="form.id ? '留空表示不修改' : '在厂商控制台创建，加密存本机'">
          <a-input-password v-model:value="form.api_key" placeholder="sk-..." />
        </a-form-item>
        <div v-if="presetDocs" class="page-tip" style="margin-bottom: 12px">
          服务地址自动使用官方端点（{{ form.base_url || '预设' }}），
          <a :href="presetDocs" target="_blank" rel="noreferrer">查看 {{ form.vendor }} 官方文档</a>
        </div>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../../api'
import { fmtTime } from '../../utils/format'

const tab = ref('providers')
const providers = ref([])
const ollamaUrl = 'http://localhost:11434'
const presets = ref([])
const pulling = ref('')
const testing = ref('')
const editing = ref(false)
const saving = ref(false)
const form = reactive({ id: '', vendor: 'deepseek', name: '', base_url: '', api_key: '', enabled: true, extra_models_text: '' })

const days = ref(7)
const page = ref(1)
const usage = reactive({})

const presetOptions = computed(() => presets.value.map((p) => ({ value: p.code, label: p.name })))
const presetDocs = computed(() => presets.value.find((x) => x.code === form.vendor)?.docs || '')

const usageCards = computed(() => {
  const s = usage.summary || {}
  return [
    { label: '调用次数', value: s.calls ?? 0, sub: s.fails ? `${s.fails} 次失败` : '全部成功' },
    { label: '总 Tokens', value: fmtNum(s.total_tokens ?? 0), sub: `输入 ${fmtNum(s.prompt_tokens ?? 0)} / 输出 ${fmtNum(s.completion_tokens ?? 0)}` },
    { label: '平均延迟', value: (s.avg_latency_ms ?? 0) + ' ms', sub: '成功请求均值' },
    { label: '服务商', value: providers.value.length + 1, sub: '含本地 Ollama' },
  ]
})

function fmtNum(n) {
  n = n || 0
  return n >= 10000 ? (n / 1000).toFixed(1) + 'k' : String(n)
}
const maxOf = (key) => Math.max(1, ...(usage[key] || []).map((x) => (key === 'by_model' ? x.tokens : x.calls)))
const barWidth = (v, key = 'by_model') => `${Math.max(2, Math.round((v / maxOf(key)) * 100))}%`

async function load() {
  providers.value = await http.get('/llm/providers')
  for (const p of providers.value) {
    try {
      const d = await http.post(`/llm/${p.id}/models`)
      p.models = d.models
      p.err = d.error
    } catch { p.models = [] }
  }
}

async function pull(p) {
  pulling.value = p.id
  try {
    const d = await http.post(`/llm/${p.id}/models`)
    p.models = d.models
    p.err = d.error
    d.cached ? message.info(`命中缓存，${d.models.length} 个模型`) : message.success(`拉取成功，${d.models.length} 个模型`)
  } finally {
    pulling.value = ''
  }
}

async function test(p) {
  testing.value = p.id
  try {
    const d = await http.post(`/llm/${p.id}/test`)
    message.success(`连接正常：${d.models_count} 个模型，对话 ${d.latency_ms}ms`)
  } catch { /* 拦截器已提示 */ } finally {
    testing.value = ''
  }
}

function openCreate() {
  Object.assign(form, { id: '', vendor: 'deepseek', name: '', base_url: '', api_key: '', enabled: true, extra_models_text: '' })
  onVendorChange()
  editing.value = true
}
function openEdit(p) {
  Object.assign(form, {
    id: p.id, vendor: p.vendor, name: p.name, base_url: p.base_url, api_key: '',
    enabled: p.enabled, extra_models_text: (p.extra_models || []).join('\n'),
  })
  editing.value = true
}
function onVendorChange() {
  const preset = presets.value.find((x) => x.code === form.vendor)
  if (!form.id) {
    form.base_url = preset?.base_url || ''
    if (!form.name) form.name = preset?.name || ''
  }
}

async function save() {
  if (!form.name.trim()) return message.warning('请填写显示名')
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(), vendor: form.vendor, base_url: form.base_url.trim(),
      api_key: form.api_key.trim(), enabled: form.enabled,
      extra_models: form.extra_models_text.split('\n').map((x) => x.trim()).filter(Boolean),
    }
    if (form.id) await http.put(`/llm/${form.id}`, payload)
    else await http.post('/llm/providers', payload)
    message.success('已保存')
    editing.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function del(p) {
  await http.delete(`/llm/${p.id}`)
  message.success('已删除')
  await load()
}

async function loadUsage(p = 1) {
  page.value = p
  const d = await http.get('/llm/usage', { params: { days: days.value, page: p, size: 20 } })
  Object.assign(usage, d)
}
const onPage = (pg) => loadUsage(pg.current)

onMounted(async () => {
  presets.value = await http.get('/llm/presets')
  await load()
  await loadUsage(1)
})
</script>

<style lang="less" scoped>
@import '../../styles/variables.less';

.prov-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }

</style>

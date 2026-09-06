<template>
  <div class="canvas-page">
    <!-- 顶栏 -->
    <div class="canvas-bar">
      <a-space>
        <a-dropdown>
          <a-button type="primary"><PlusOutlined /> 添加节点</a-button>
          <template #overlay>
            <a-menu @click="({ key }) => addNode(key)">
              <a-menu-item key="knowledge_retrieve">知识检索</a-menu-item>
              <a-menu-item key="tool_research">工具研究（ReAct）</a-menu-item>
              <a-menu-item key="llm">LLM 节点</a-menu-item>
              <a-menu-item key="review">质检门控</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
        <span class="page-tip">拖拽连线 · 点选节点在右侧配置 · 变量：
          <code v-for="v in varHints" :key="v">{{ v }}</code>
        </span>
      </a-space>
      <a-space>
        <a-button @click="runOpen = true">试运行</a-button>
        <a-button @click="reset">恢复默认编排</a-button>
        <a-button type="primary" :loading="saving" @click="save">保存编排</a-button>
      </a-space>
    </div>

    <div class="canvas-body">
      <!-- 画布 -->
      <div class="canvas-main" :style="{ width: selected ? '64%' : '100%' }">
        <div class="canvas-wrap">
          <VueFlow v-model:nodes="nodes" v-model:edges="edges" fit-view-on-init
                   :max-zoom="1.6" :min-zoom="0.4"
                   @connect="onConnect" @node-click="onNodeClick"
                   @pane-click="selected = null">
            <template #node-custom="props">
              <div class="flow-node" :style="{ borderTopColor: typeMeta(props.data.ntype).color }">
                <div class="fn-head">
                  <component :is="typeMeta(props.data.ntype).icon" :style="{ color: typeMeta(props.data.ntype).color }" />
                  <span class="fn-name">{{ props.data.title }}</span>
                </div>
                <div class="fn-desc">{{ typeMeta(props.data.ntype).desc }}</div>
                <div v-if="props.data.ntype !== 'start' && props.data.ntype !== 'answer'" class="fn-handles-hint">
                  <Handle type="target" :position="Position.Left" />
                </div>
                <Handle type="source" :position="Position.Right" />
              </div>
            </template>
          </VueFlow>
        </div>
      </div>

      <!-- 配置面板 -->
      <div class="cfg-side" v-if="selected">
        <a-card size="small" class="cfg-panel">
          <template #title>
            <a-input v-model:value="selected.data.title" size="small" variant="borderless"
                     style="font-weight: 700; padding: 0" />
          </template>
          <template #extra>
            <a-popconfirm v-if="!['start', 'answer'].includes(selected.data.ntype)"
                          title="删除节点及其连线？" @confirm="delNode">
              <a style="color: #ff4d4f"><DeleteOutlined /></a>
            </a-popconfirm>
          </template>

          <template v-if="selected.data.ntype === 'knowledge_retrieve'">
            <a-form layout="vertical">
              <a-form-item label="检索条数 top_k">
                <a-input-number v-model:value="selected.data.config.top_k" :min="1" :max="10" style="width: 100%" />
              </a-form-item>
              <div class="page-tip">检索全部知识库：个人档案 + 书籍知识，结果写入 <code>{{ varHints[3] }}</code> 与 <code>{{ varHints[4] }}</code></div>
            </a-form>
          </template>

          <template v-else-if="selected.data.ntype === 'tool_research'">
            <a-form layout="vertical">
              <a-form-item label="最多研究轮数">
                <a-input-number v-model:value="selected.data.config.max_steps" :min="1" :max="6" style="width: 100%" />
              </a-form-item>
              <a-form-item label="可用工具（不选 = 全部）">
                <a-select v-model:value="selected.data.config.tools" mode="multiple"
                          :options="toolOptions" placeholder="留空使用全部工具" />
              </a-form-item>
              <div class="page-tip">结果写入 <code>{{ varHints[5] }}</code></div>
            </a-form>
          </template>

          <template v-else-if="selected.data.ntype === 'llm'">
            <a-form layout="vertical">
              <a-form-item label="System 提示（支持变量）">
                <a-textarea v-model:value="selected.data.config.system" :rows="4" class="mono" />
              </a-form-item>
              <a-form-item label="User 提示模板（支持变量）">
                <a-textarea v-model:value="selected.data.config.prompt" :rows="7" class="mono" />
              </a-form-item>
              <a-form-item label="输出写入">
                <a-select v-model:value="selected.data.config.output"
                          :options="[{ value: 'candidates', label: 'candidates（解析为候选回复）' },
                                     { value: 'research', label: 'research（作为调研上下文）' },
                                     { value: 'fail_reason', label: 'fail_reason' }]" />
              </a-form-item>
            </a-form>
          </template>

          <template v-else-if="selected.data.ntype === 'review'">
            <a-form layout="vertical">
              <a-form-item label="检查清单（支持变量）">
                <a-textarea v-model:value="selected.data.config.checklist" :rows="4" />
              </a-form-item>
              <a-form-item label="FAIL 最多重写次数（沿 fail 边）">
                <a-input-number v-model:value="selected.data.config.max_redraft" :min="0" :max="3" style="width: 100%" />
              </a-form-item>
              <div class="page-tip">
                PASS 走标记为 pass 的出线，FAIL 走标记为 fail 的出线（保存后在编排 JSON 中维护连线标记；
                无 fail 线时 FAIL 直接放行）。
              </div>
            </a-form>
          </template>

          <template v-else>
            <div class="page-tip">
              {{ selected.data.ntype === 'start'
                ? "入口节点：自动装配 message / person / history 变量。"
                : "出口节点：把 candidates 变量解析为 3 个候选回复并结束。" }}
            </div>
          </template>
        </a-card>
      </div>
    </div>

    <!-- 试运行 -->
    <a-modal v-model:open="runOpen" title="试运行当前编排" :footer="null" :width="680">
      <a-textarea v-model:value="runMessage" :rows="2" placeholder="输入一条对方消息进行试运行" />
      <a-button type="primary" style="margin-top: 10px" :loading="running" @click="runTest">运行</a-button>
      <div v-if="runResult" style="margin-top: 14px">
        <div class="page-tip">耗时 {{ (runResult.elapsed_ms / 1000).toFixed(1) }}s · 技能 {{ runResult.skill }} · 轨迹 {{ runResult.trace.length }} 步</div>
        <div v-for="(c, i) in runResult.candidates" :key="i" class="run-cand">{{ i + 1 }}. {{ c }}</div>
        <details>
          <summary class="page-tip" style="cursor: pointer">执行轨迹（{{ runResult.trace.length }}）</summary>
          <div v-for="(t, i) in runResult.trace" :key="i" class="usage-row">
            <span class="usage-name" style="width: 130px">{{ t.node }}{{ t.tool ? ' · ' + t.tool : '' }}</span>
            <span class="usage-val" style="width: auto; flex: 1; text-align: left">{{ t.detail }}</span>
          </div>
        </details>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { VueFlow, useVueFlow, Handle, Position } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../../api'

const { addEdges, removeEdges, findNode, getSelectedEdges } = useVueFlow()

const VARS = ['message', 'person', 'history', 'knowledge', 'docs', 'research', 'candidates', 'fail_reason']
const varHints = VARS.map((v) => '{{' + v + '}}')

const TYPE_META = {
  start: { label: '开始', color: '#07c160', desc: '装配消息与上下文' },
  knowledge_retrieve: { label: '知识检索', color: '#1668dc', desc: '个人档案 + 知识库向量检索' },
  tool_research: { label: '工具研究', color: '#13c2c2', desc: 'ReAct 循环调用工具收集情报' },
  llm: { label: 'LLM', color: '#d46b08', desc: '渲染提示词调用大模型' },
  review: { label: '质检门控', color: '#5b6672', desc: 'PASS/FAIL 条件分支' },
  answer: { label: '输出', color: '#d93026', desc: '候选清洗并结束' },
}

const DEFAULT_CFG = {
  knowledge_retrieve: () => ({ top_k: 4 }),
  tool_research: () => ({ max_steps: 3, tools: [] }),
  llm: () => ({ title: 'LLM 节点', system: '', prompt: '【对方消息】{{message}}', output: 'candidates' }),
  review: () => ({ checklist: '检查金钱承诺、说教、违反雷区；只输出 PASS 或 FAIL:原因', max_redraft: 1 }),
}

let idSeq = 1
const nextId = (t) => `${t}_${idSeq++}_${Math.random().toString(36).slice(2, 6)}`

const nodes = ref([])
const edges = ref([])
const selected = ref(null)
const saving = ref(false)
const toolOptions = ref([])

const runOpen = ref(false)
const runMessage = ref('在吗？周末有空吗，来我家吃饭')
const running = ref(false)
const runResult = ref(null)

const typeMeta = (t) => TYPE_META[t] || { label: t, color: '#98a2ae', desc: '' }

function addNode(ntype) {
  const id = nextId(ntype)
  nodes.value.push({
    id, type: 'custom',
    position: { x: 240 + Math.random() * 220, y: 60 + Math.random() * 200 },
    data: { ntype, title: TYPE_META[ntype].label,
            config: (DEFAULT_CFG[ntype] || (() => ({})))() },
  })
  selected.value = nodes.value[nodes.value.length - 1]
}

function onNodeClick({ node }) {
  if (!node.data.config) node.data.config = {}
  selected.value = node
}
function onConnect(params) {
  addEdges([{ ...params, animated: true }])
}
async function delNode() {
  const node = selected.value
  if (!node) return
  removeEdges(edges.value.filter((e) => e.source === node.id || e.target === node.id))
  nodes.value = nodes.value.filter((n) => n.id !== node.id)
  selected.value = null
}

async function save() {
  // review 节点出线标记检查（存进 edge.label，运行时按 pass/fail 分流）
  for (const e of edges.value) {
    const src = nodes.value.find((x) => x.id === e.source)
    if (src?.data.ntype === 'review' && e.label &&
        !['pass', 'fail'].includes(String(e.label).toLowerCase())) {
      return message.warning('质检节点出线标记只能是 pass / fail（选中连线后在左侧设置）')
    }
  }
  saving.value = true
  try {
    await http.put('/ext/canvas', {
      nodes: nodes.value.map((n) => ({
        id: n.id, type: n.data.ntype,
        x: Math.round(n.position.x), y: Math.round(n.position.y),
        config: n.data.config || {},
      })),
      edges: edges.value.map((e) => ({ source: e.source, target: e.target, label: e.label || '' })),
    })
    message.success('编排已保存，下一次智能体对话即按此流程执行')
  } finally {
    saving.value = false
  }
}

function toFlow(cfg) {
  return cfg.nodes.map((n) => ({
    id: n.id, type: 'custom',
    position: { x: n.x ?? 0, y: n.y ?? 0 },
    data: { ntype: n.type, title: n.config?.title || TYPE_META[n.type]?.label || n.type,
            config: n.config || {} },
  }))
}

async function reset() {
  const d = await http.get('/ext/canvas') // v1 旧文件自动升级为默认 v2 模板
  nodes.value = toFlow(d)
  edges.value = d.edges.map((e, i) => ({ id: `e${i}`, ...e, animated: true }))
  selected.value = null
  message.info('已加载默认编排，点「保存编排」固化')
}

async function runTest() {
  running.value = true
  runResult.value = null
  try {
    runResult.value = await http.post('/ext/canvas/test', { message: runMessage.value, person: '' })
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  const cfg = await http.get('/ext/canvas')
  nodes.value = toFlow(cfg)
  edges.value = cfg.edges.map((e, i) => ({ id: `e${i}`, ...e, animated: true }))
  const tools = await http.get('/agent/tools')
  toolOptions.value = [...tools.builtin, ...tools.plugin, ...tools.mcp]
    .map((t) => ({ value: t.name.replace(/^(plugin|mcp):/, ''), label: t.name }))
})
</script>

<style lang="less" scoped>
@import '../../styles/variables.less';

.canvas-page { display: flex; flex-direction: column; }
.canvas-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.canvas-body { display: flex; gap: 0; margin: 0 !important; }
.canvas-main { transition: width 0.2s; }
.canvas-wrap {
  height: calc(100vh - @header-h - 36px - 76px);
  min-height: 460px;
  background: @panel;
  border: 1px solid @border;
  border-radius: @radius;
  background-image: radial-gradient(circle, #e8ebef 1px, transparent 1px);
  background-size: 18px 18px;
}

.cfg-side { padding-left: 12px; width: 36%; }
.cfg-panel { max-height: calc(100vh - @header-h - 60px); overflow: auto; }

.flow-node {
  width: 200px;
  background: @panel;
  border: 1px solid @border-strong;
  border-top: 3px solid @green;
  border-radius: @radius;
  padding: 8px 10px;
  box-shadow: 0 2px 8px rgba(31, 45, 61, 0.10);
  .fn-head { display: flex; align-items: center; gap: 6px; margin-bottom: 3px;
    .fn-name { font-weight: 700; font-size: 13px; color: @text-1; } }
  .fn-desc { font-size: 11.5px; color: @text-3; line-height: 1.4; }
  .fn-handles-hint { height: 1px; }
}

.run-cand {
  border: 1px solid @border; border-radius: @radius; padding: 8px 10px;
  margin-top: 6px; background: #fbfcfd; font-size: 13.5px;
}
</style>

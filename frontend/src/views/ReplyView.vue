<template>
  <div class="chat-page">
    <!-- 会话工具条 -->
    <div class="chat-toolbar">
      <span class="field">
        <label>对话对象</label>
        <a-auto-complete v-model:value="person" :options="persons.map((p) => ({ value: p }))"
                         placeholder="谁在和你聊（匹配关系档案）" style="width: 200px" />
      </span>
      <span class="field">
        <label>引擎</label>
        <a-radio-group v-model:value="engine" size="small" button-style="solid">
          <a-radio-button value="agent">智能体</a-radio-button>
          <a-radio-button value="fast">快速</a-radio-button>
        </a-radio-group>
      </span>
      <span class="field">
        <label>模型</label>
        <a-select v-model:value="model" :options="models" style="width: 230px"
                  show-search :filter-option="(i, o) => o.label.toLowerCase().includes(i.toLowerCase())" />
      </span>
      <span class="spacer" />
      <a-button size="small" @click="clearChat" :disabled="busy">清空对话</a-button>
    </div>

    <!-- 消息流 -->
    <div class="chat-scroll" ref="scrollRef">
      <div v-if="!messages.length" class="chat-empty">
        <div class="empty-title">把对方发来的消息粘贴到下面</div>
        <div class="empty-sub">AI 会结合你的个人档案和知识库给出 3 个候选回复，点选即用（自动复制）</div>
      </div>

      <template v-for="(m, i) in messages" :key="i">
        <!-- 对方 -->
        <div v-if="m.role === 'other'" class="row left">
          <div class="avatar other">{{ (person || '对')[0] }}</div>
          <div class="bubble other">{{ m.text }}</div>
        </div>

        <!-- AI 建议：候选选择条 -->
        <div v-if="m.role === 'assist'" class="row left">
          <div class="avatar ai">AI</div>
          <div class="assist">
            <div v-if="m.pending" class="typing">
              <span /><span /><span />
              <em v-if="m.pendingTip" class="pending-tip">{{ m.pendingTip }}</em>
            </div>
            <div v-if="m.pending && m.trace.length" class="trace live">
              <div v-for="(t, ti) in m.trace" :key="ti" class="trace-row">
                <span class="trace-node">{{ t.node }}{{ t.tool ? '·' + t.tool : '' }}</span>
                <span class="trace-detail">{{ t.detail }}</span>
              </div>
            </div>
            <template v-else>
              <div class="assist-head">
                <a-tag v-if="m.skill" color="green" style="margin-right: 6px">{{ m.skill }}</a-tag>
                3 个候选回复 —— 点选即复制发送
                <span v-if="m.elapsed" style="margin-left: 6px">（{{ (m.elapsed / 1000).toFixed(1) }}s）</span>
              </div>
              <div class="candidates">
                <div v-for="(c, ci) in m.candidates" :key="ci" class="cand" @click="choose(m, ci)">
                  <span class="cand-tag">{{ tags[ci] || '候选 ' + (ci + 1) }}</span>
                  <span class="cand-text">{{ c }}</span>
                </div>
              </div>
              <div class="assist-foot">
                <a @click="regenerate(m)">换一批</a>
                <a-divider type="vertical" />
                <a @click="m.showSrc = !m.showSrc">检索依据（{{ m.sources.length }}）</a>
                <a-divider type="vertical" />
                <a @click="m.showTrace = !m.showTrace">执行轨迹（{{ (m.trace || []).length }}）</a>
              </div>
              <div v-if="m.showTrace" class="trace">
                <div v-for="(t, ti) in m.trace" :key="ti" class="trace-row">
                  <span class="trace-node">{{ t.node }}{{ t.tool ? '·' + t.tool : '' }}</span>
                  <span class="trace-detail">{{ t.detail }}</span>
                </div>
              </div>
              <div v-if="m.showSrc" class="src">
                <div v-for="(s, si) in m.sources" :key="si" class="src-item">
                  <b>{{ s.kb_name }} · {{ s.source }}</b>
                  <span v-if="s.chapter"> · {{ s.chapter }}</span>
                  <p>{{ s.text.slice(0, 120) }}…</p>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- 我方（选用的回复） -->
        <div v-if="m.role === 'me'" class="row right">
          <div class="bubble me">
            {{ m.text }}
            <span class="copied" v-if="m.justCopied">已复制</span>
          </div>
          <div class="avatar me-av">{{ (auth.user?.nickname || '我')[0] }}</div>
        </div>
      </template>
    </div>

    <!-- 输入区 -->
    <div class="chat-input">
      <a-textarea
        v-model:value="draft" :rows="2"
        placeholder="粘贴对方发来的消息，Enter 或点击「生成回复」"
        @keydown.enter.exact.prevent="send"
      />
      <div class="input-bar">
        <span class="hint">Enter 发送 · 历史对话会自动作为上下文</span>
        <a-button type="primary" :loading="busy" :disabled="!draft.trim()" @click="send">生成回复</a-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import http from '../api'
import { useAuthStore } from '../stores/auth'

const tags = ['稳妥得体', '幽默拉近距离', '简短直接']
const auth = useAuthStore()

const person = ref('')
const model = ref('')
const engine = ref(localStorage.getItem('chatkb_engine') || 'agent')
const persons = ref([])
const models = ref([])
const messages = reactive([])
const draft = ref('')
watch(engine, (v) => localStorage.setItem('chatkb_engine', v))
const busy = ref(false)
const scrollRef = ref(null)

const lastOther = () => [...messages].reverse().find((m) => m.role === 'other')

function scrollBottom() {
  nextTickSafe()
}
function nextTickSafe() {
  import('vue').then(({ nextTick }) => {
    nextTick(() => {
      const el = scrollRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  })
}

async function send() {
  const text = draft.value.trim()
  if (!text || busy.value) return
  messages.push({ role: 'other', text })
  draft.value = ''
  await ask(text)
}

async function regenerate(m) {
  if (busy.value) return
  const target = lastOther()
  if (!target) return
  await ask(target.text, m)
}

const stripThink = (s) => s
  .replace(/<think>[\s\S]*?<\/think>/g, '')
  .replace(/<think>[\s\S]*$/, '')

async function ask(text, existingAssist) {
  busy.value = true
  const turn = existingAssist || (() => {
    const t = reactive({ role: 'assist', pending: true, candidates: [], sources: [], showSrc: false, showTrace: true, trace: [], skill: '', elapsed: 0, pendingTip: '', streamingText: '' })
    messages.push(t)
    return t
  })()
  turn.pending = true
  turn.streamingText = ''
  scrollBottom()
  try {
    // 上下文 = 本轮消息之前的所有已确定对话（最多 10 条）
    const history = messages.slice(0, messages.indexOf(turn))
      .filter((m) => m.role === 'other' || m.role === 'me')
      .map((m) => (m.role === 'other' ? `对方：${m.text}` : `我：${m.text}`))
      .slice(-10)
      .join('\n')

    // 统一流式：轨迹与候选 token 都逐步推送
    const token = localStorage.getItem('chatkb_token')
    const resp = await fetch('/api/agent/reply/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        message: text, person: person.value, history,
        model: model.value || undefined, engine: engine.value,
      }),
    })
    if (!resp.ok) throw new Error('HTTP ' + resp.status)
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let fullText = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()
      for (const line of lines) {
        if (!line.trim()) continue
        let ev
        try { ev = JSON.parse(line) } catch { continue }
        if (ev.type === 'trace') {
          turn.trace.push(ev)
          turn.pendingTip = `${ev.node}${ev.tool ? ' · ' + ev.tool : ''}`
          scrollBottom()
        } else if (ev.type === 'token') {
          fullText += ev.delta
          turn.streamingText = stripThink(fullText)
          scrollBottom()
        } else if (ev.type === 'done') {
          turn.candidates = ev.candidates
          turn.sources = ev.sources || []
          turn.skill = ev.skill
          turn.elapsed = ev.elapsed_ms
          turn.streamingText = ''
          scrollBottom()
        } else if (ev.type === 'error') {
          message.error(ev.detail || '执行失败')
        }
      }
    }
  } catch (e) {
    message.error('执行失败：' + (e.message || ''))
  } finally {
    turn.pending = false
    busy.value = false
    scrollBottom()
  }
}

async function choose(turn, ci) {
  const text = turn.candidates[ci]
  messages.push({ role: 'me', text, justCopied: true })
  scrollBottom()
  try {
    await navigator.clipboard.writeText(text)
    message.success('已复制，去微信粘贴发送')
    setTimeout(() => messages.forEach((m) => (m.justCopied = false)), 1500)
  } catch {
    message.success('已加入对话（浏览器未授权剪贴板，请手动复制）')
  }
}

function clearChat() {
  messages.splice(0)
}

onMounted(async () => {
  const s = await http.get('/system/settings')
  // 个人模型配置持久化在本地；没有历史选择时默认本地 Ollama
  const saved = localStorage.getItem('chatkb_model')
  try {
    models.value = await http.get('/llm/models')
  } catch {
    models.value = [{ value: `ollama|${s.chat_model}`, label: `本地 Ollama · ${s.chat_model}` }]
  }
  const fallback =
    models.value.find((m) => /highspeed|flash|turbo/i.test(m.label))?.value
    || models.value.find((m) => !m.value.startsWith('ollama|'))?.value
    || models.value[0]?.value
    || `ollama|${s.chat_model}`
  model.value = saved && models.value.some((m) => m.value === saved) ? saved : fallback
  watch(model, (v) => localStorage.setItem('chatkb_model', v))
  persons.value = await http.get('/profiles/persons')
})
</script>

<style lang="less" scoped>
@import '../styles/variables.less';

.chat-page {
  height: calc(100vh - @header-h - 36px - 28px); // 头 + 底栏 + content 上下 margin
  min-height: 520px;
  display: flex; flex-direction: column;
  background: @panel;
  border: 1px solid @border;
  border-radius: @radius;
  overflow: hidden;
}

.chat-toolbar {
  display: flex; align-items: flex-end; gap: 16px;
  padding: 10px 16px;
  border-bottom: 1px solid @border;
  .field { display: flex; flex-direction: column; gap: 3px;
    label { font-size: 12px; color: @text-3; letter-spacing: 0.05em; } }
  .spacer { flex: 1; }
}

.chat-scroll {
  flex: 1; overflow-y: auto;
  padding: 20px 24px 12px;
  background: @bg;
}

.chat-empty {
  text-align: center; margin-top: 18vh; color: @text-3;
  .empty-title { font-size: 15px; color: @text-2; margin-bottom: 6px; }
  .empty-sub { font-size: 12.5px; }
}

.row { display: flex; gap: 10px; margin-bottom: 16px;
  &.right { flex-direction: row-reverse; } }

.avatar {
  width: 34px; height: 34px; border-radius: 4px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; color: #fff;
  &.other { background: #8d99a8; }
  &.me-av { background: @green; }
  &.ai { background: @text-1; font-family: @display-font; letter-spacing: 0.05em; }
}

.bubble {
  max-width: 62%;
  padding: 9px 13px;
  font-size: 14px; line-height: 1.65;
  white-space: pre-wrap; word-break: break-word;
  position: relative;
  &.other { background: @panel; border: 1px solid @border; border-radius: 0 @radius @radius @radius; }
  &.me { background: @green-bg; border: 1px solid #cdebd9; border-radius: @radius 0 @radius @radius; color: @text-1; }
  .copied { position: absolute; top: -22px; right: 0; font-size: 11px; color: @ok; }
}

.assist {
  max-width: 72%;
  background: @panel;
  border: 1px dashed @border-strong;
  border-radius: 0 @radius @radius @radius;
  padding: 10px 12px;
}
.assist-head { font-size: 12px; color: @text-3; margin-bottom: 8px; letter-spacing: 0.05em; }
.candidates {
  display: flex; flex-direction: column; gap: 6px;
  .cand {
    display: flex; align-items: flex-start; gap: 8px;
    border: 1px solid @border; border-radius: @radius;
    padding: 8px 10px; cursor: pointer; background: #fbfcfd;
    transition: border-color 0.15s, background 0.15s;
    &:hover { border-color: @green; background: @green-bg; }
    .cand-tag { flex-shrink: 0; font-size: 11px; color: @green-dark; background: @green-bg;
      border-radius: 3px; padding: 1px 6px; margin-top: 2px; }
    .cand-text { font-size: 13.5px; line-height: 1.6; }
  }
}
.assist-foot { margin-top: 8px; font-size: 12px;
  a { color: @text-2; &:hover { color: @green-dark; } } }
.src { margin-top: 8px; border-top: 1px solid @border; padding-top: 8px;
  .src-item { font-size: 12px; color: @text-2; margin-bottom: 6px;
    b { color: @text-1; font-weight: 600; }
    p { margin: 2px 0 0; color: @text-3; } } }

.trace { margin-top: 8px; border-top: 1px solid @border; padding-top: 8px;
  .trace-row { display: flex; gap: 8px; font-size: 12px; padding: 2px 0;
    .trace-node { flex-shrink: 0; width: 110px; color: @green-dark; font-family: @display-font; }
    .trace-detail { color: @text-3; word-break: break-all; } } }

.typing { display: inline-flex; align-items: center; gap: 4px; padding: 4px 0;
  span { width: 6px; height: 6px; border-radius: 50%; background: @text-3;
    animation: blink 1.2s infinite;
    &:nth-child(2) { animation-delay: 0.2s; }
    &:nth-child(3) { animation-delay: 0.4s; } }
  .pending-tip { font-style: normal; margin-left: 8px; font-size: 12px; color: @text-3;
    font-family: @display-font; } }
@keyframes blink { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }

.chat-input {
  border-top: 1px solid @border;
  padding: 12px 16px;
  background: @panel;
  :deep(.ant-input) { resize: none; border-radius: @radius; }
  .input-bar { display: flex; align-items: center; justify-content: space-between; margin-top: 8px;
    .hint { font-size: 12px; color: @text-3; } }
}
</style>

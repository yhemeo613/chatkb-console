<template>
  <a-row :gutter="16">
    <a-col :span="10">
      <a-card title="MCP 服务器" size="small">
        <template #extra>
          <a-space>
            <a-button size="small" type="primary" @click="adding = true"><PlusOutlined /> 添加</a-button>
            <a-button size="small" :loading="refreshing" @click="refresh">连接全部</a-button>
          </a-space>
        </template>
        <a-empty v-if="!servers.length"
                 description="未配置服务器。MCP 通过 stdio/SSE 接入，例如 npx 启动 @modelcontextprotocol/server-filesystem" />
        <div v-for="s in servers" :key="s.name" class="srv">
          <div>
            <b>{{ s.name }}</b>
            <a-tag :color="s.connected ? 'green' : 'orange'" style="margin-left: 8px">
              {{ s.connected ? '已连接' : '未连接' }}
            </a-tag>
            <div class="page-tip">{{ s.transport }} · {{ s.command }} {{ (s.args || []).join(' ') }}</div>
          </div>
          <a-popconfirm title="删除该 server？" @confirm="del(s)">
            <a style="color: #ff4d4f">删除</a>
          </a-popconfirm>
        </div>
      </a-card>
    </a-col>
    <a-col :span="14">
      <a-card title="发现的工具（连接后自动进入智能体工具箱）" size="small">
        <a-empty v-if="!tools.length" description="暂无 MCP 工具" />
        <a-table :data-source="tools" row-key="name" size="small" :pagination="false">
          <a-table-column title="工具" data-index="name" :width="170" />
          <a-table-column title="来源" data-index="server" :width="110" />
          <a-table-column title="描述" data-index="description" ellipsis />
        </a-table>
      </a-card>
    </a-col>
  </a-row>

  <a-modal v-model:open="adding" title="添加 MCP 服务器（stdio）" @ok="add">
    <a-form layout="vertical">
      <a-form-item label="名称" required><a-input v-model:value="form.name" placeholder="例：filesystem" /></a-form-item>
      <a-form-item label="启动命令" required><a-input v-model:value="form.command" placeholder="npx" /></a-form-item>
      <a-form-item label="参数（每行一个）">
        <a-textarea v-model:value="argsText" :rows="3" placeholder="-y&#10;@modelcontextprotocol/server-filesystem&#10;C:/docs" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../../api'

const servers = ref([])
const tools = ref([])
const adding = ref(false)
const refreshing = ref(false)
const form = reactive({ name: '', command: '', argsText: '' })

async function load() {
  const d = await http.get('/agent/mcp')
  servers.value = d.servers
  tools.value = d.tools
}
async function refresh() {
  refreshing.value = true
  try {
    const d = await http.post('/agent/mcp/refresh')
    const ok = d.results.filter((r) => r.ok).length
    message.success(`已连接 ${ok}/${d.results.length} 个 server`)
    await load()
  } finally { refreshing.value = false }
}
async function add() {
  if (!form.name.trim() || !form.command.trim()) return message.warning('请填写名称和命令')
  await http.post('/agent/mcp/servers', {
    name: form.name.trim(), command: form.command.trim(),
    args: form.argsText.split('\n').map((x) => x.trim()).filter(Boolean),
  })
  adding.value = false
  message.success('已保存，点击「连接全部」建立会话')
  await load()
}
async function del(s) {
  await http.delete(`/ext/mcp/servers/${encodeURIComponent(s.name)}`)
  message.success('已删除')
  await load()
}
onMounted(load)
</script>

<style lang="less" scoped>
@import '../../styles/variables.less';
.srv { display: flex; justify-content: space-between; align-items: flex-start;
  padding: 8px 0; border-bottom: 1px dashed @border; &:last-child { border-bottom: none; } }
</style>

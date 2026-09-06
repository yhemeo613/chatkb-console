<template>
  <div>
    <div style="margin-bottom: 14px">
      <a-button type="primary" @click="openCreate"><PlusOutlined /> 新建插件</a-button>
      <span class="page-tip" style="margin-left: 12px">JSON 定义 HTTP 端点即成为智能体可调用工具，保存即生效</span>
    </div>
    <a-table :data-source="plugins" row-key="name" :pagination="false" size="middle">
      <a-table-column title="工具名" data-index="name" :width="140" />
      <a-table-column title="描述" data-index="description" ellipsis />
      <a-table-column title="方法" :width="90">
        <template #default="{ record }"><a-tag>{{ record.method }}</a-tag></template>
      </a-table-column>
      <a-table-column title="端点" data-index="endpoint" ellipsis />
      <a-table-column title="参数" :width="160">
        <template #default="{ record }">{{ Object.keys(record.params || {}).join('、') || '—' }}</template>
      </a-table-column>
      <a-table-column title="操作" :width="130">
        <template #default="{ record }">
          <a-space>
            <a @click="openEdit(record)">编辑</a>
            <a-popconfirm title="删除该插件？" @confirm="del(record)"><a style="color: #ff4d4f">删除</a></a-popconfirm>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:open="editing" :title="form.stem ? `编辑：${form.stem}` : '新建插件'" @ok="save" :width="640">
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="工具名" required><a-input v-model:value="form.name" placeholder="英文标识，例：weather" /></a-form-item></a-col>
          <a-col :span="12">
            <a-form-item label="方法">
              <a-select v-model:value="form.method" :options="['GET', 'POST'].map((v) => ({ value: v }))" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述"><a-input v-model:value="form.description" placeholder="给模型看的工具说明" /></a-form-item>
        <a-form-item label="端点（{参数} 占位）" required>
          <a-input v-model:value="form.endpoint" placeholder="https://wttr.in/{city}?format=3" />
        </a-form-item>
        <a-form-item label="参数（JSON，键=参数名，值=描述）">
          <a-textarea v-model:value="paramsText" class="mono" :rows="3" placeholder='{"city": "城市名"}' />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../../api'

const plugins = ref([])
const editing = ref(false)
const paramsText = ref('{}')
const form = reactive({ stem: '', name: '', description: '', method: 'GET', endpoint: '' })

async function load() { plugins.value = await http.get('/ext/plugins') }
function openCreate() {
  Object.assign(form, { stem: '', name: '', description: '', method: 'GET', endpoint: '' })
  paramsText.value = '{}'
  editing.value = true
}
function openEdit(record) {
  Object.assign(form, { stem: record.name, name: record.name, description: record.description,
                        method: record.method, endpoint: record.endpoint })
  paramsText.value = JSON.stringify(record.params || {}, null, 2)
  editing.value = true
}
async function save() {
  let params = {}
  try { params = JSON.parse(paramsText.value || '{}') } catch { return message.warning('参数不是合法 JSON') }
  const payload = { ...form, params }
  const stem = form.stem || form.name.trim()
  await http.post(`/ext/plugins/${encodeURIComponent(stem)}`, payload)
  message.success('已保存，下次智能体运行即生效')
  editing.value = false
  await load()
}
async function del(record) {
  await http.delete(`/ext/plugins/${encodeURIComponent(record.name)}`)
  message.success('已删除')
  await load()
}
onMounted(load)
</script>

<style lang="less" scoped>
@import '../../styles/variables.less';
</style>

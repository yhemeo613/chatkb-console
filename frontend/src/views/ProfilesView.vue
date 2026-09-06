<template>
  <a-row :gutter="16">
    <a-col :span="7">
      <a-card title="档案文件">
        <template #extra>
          <a-button size="small" type="primary" @click="creating = true"><PlusOutlined /></a-button>
        </template>
        <a-list :data-source="profiles" row-key="name" size="small">
          <template #renderItem="{ item }">
            <a-list-item style="cursor: pointer" :class="{ active: item.name === current }" @click="open(item)">
              <a-list-item-meta>
                <template #title>{{ item.name }}</template>
                <template #description>
                  <a-tag v-if="item.person" color="orange">{{ item.person }}</a-tag>
                  <span style="color: #b4bac4; font-size: 12px">{{ fmtTime(item.updated_at) }}</span>
                </template>
              </a-list-item-meta>
              <template #actions>
                <a-popconfirm title="删除该档案？" @confirm="del(item)">
                  <a style="color: #ff4d4f" @click.stop><DeleteOutlined /></a>
                </a-popconfirm>
              </template>
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </a-col>

    <a-col :span="17">
      <a-card v-if="current">
        <template #title>{{ current }}</template>
        <template #extra>
          <a-button type="primary" :loading="saving" @click="save">保存并同步索引</a-button>
        </template>
        <a-textarea v-model:value="content" class="mono" :rows="22" style="font-size: 13px" />
        <a-typography-paragraph type="secondary" style="margin-top: 10px; font-size: 12px">
          顶部 frontmatter 里的 <code>person: 称呼</code> 用于「对话回复」时按人匹配档案；保存后自动重建个人档案索引。
        </a-typography-paragraph>
      </a-card>
      <a-empty v-else description="选择左侧档案开始编辑" style="margin-top: 80px" />
    </a-col>
  </a-row>

  <a-modal v-model:open="creating" title="新建档案" @ok="create">
    <a-form layout="vertical">
      <a-form-item label="文件名（不含 .md）" required>
        <a-input v-model:value="newName" placeholder="例：03_关系档案_老妈" />
      </a-form-item>
      <a-form-item label="person 称呼">
        <a-input v-model:value="newPerson" placeholder="例：老妈" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../api'
import { fmtTime } from '../utils/format'

const profiles = ref([])
const current = ref('')
const content = ref('')
const saving = ref(false)
const creating = ref(false)
const newName = ref('')
const newPerson = ref('')

async function load() {
  profiles.value = await http.get('/profiles')
}
async function open(item) {
  current.value = item.name
  const d = await http.get(`/profiles/${encodeURIComponent(item.name)}`)
  content.value = d.content
}
async function save() {
  saving.value = true
  try {
    await http.put(`/profiles/${encodeURIComponent(current.value)}`, { content: content.value })
    message.success('已保存，正在后台同步索引')
    await load()
  } finally {
    saving.value = false
  }
}
async function create() {
  if (!newName.value.trim()) return message.warning('请填写文件名')
  await http.post('/profiles', { name: newName.value.trim(), person: newPerson.value.trim() })
  creating.value = false
  message.success('已创建')
  await load()
}
async function del(item) {
  await http.delete(`/profiles/${encodeURIComponent(item.name)}`)
  if (current.value === item.name) { current.value = ''; content.value = '' }
  message.success('已删除')
  await load()
}

onMounted(load)
</script>

<style lang="less" scoped>
@import '../styles/variables.less';
.active { background: @green-bg; }
</style>

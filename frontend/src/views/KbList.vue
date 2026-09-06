<template>
  <div>
    <div style="margin-bottom: 16px">
      <a-button type="primary" @click="openCreate"><PlusOutlined /> 新建知识库</a-button>
    </div>

    <a-row :gutter="16">
      <a-col :span="8" v-for="kb in kbs" :key="kb.id" style="margin-bottom: 16px">
        <a-card hoverable>
          <template #title>
            <span @click="$router.push(`/kbs/${kb.id}`)" style="cursor: pointer">
              <DatabaseOutlined v-if="kb.type === 'docs'" style="color: #1668dc; margin-right: 6px" />
              <ProfileOutlined v-else style="color: #d46b08; margin-right: 6px" />
              {{ kb.name }}
            </span>
          </template>
          <template #extra>
            <a-popconfirm title="删除知识库将同时删除全部文档和索引，确定？" @confirm="del(kb)">
              <a style="color: #ff4d4f"><DeleteOutlined /></a>
            </a-popconfirm>
          </template>
          <a-tag :color="kb.type === 'persona' ? 'orange' : 'blue'">
            {{ kb.type === 'persona' ? '个人档案' : '文档知识库' }}
          </a-tag>
          <p style="color: #8a919f; min-height: 22px; margin: 10px 0">{{ kb.description || '暂无描述' }}</p>
          <a-row style="font-size: 13px; color: #4e5969">
            <a-col :span="8">文档 {{ kb.doc_count }}</a-col>
            <a-col :span="8">文本块 {{ kb.chunk_count }}</a-col>
            <a-col :span="8">向量 {{ kb.embed_model }}</a-col>
          </a-row>
          <div style="margin-top: 12px">
            <a-button size="small" type="primary" ghost @click="$router.push(`/kbs/${kb.id}`)">管理文档</a-button>
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-modal v-model:open="creating" title="新建知识库" @ok="create" :confirm-loading="busy">
      <a-form layout="vertical">
        <a-form-item label="名称" required><a-input v-model:value="form.name" placeholder="例：销售话术合集" /></a-form-item>
        <a-form-item label="类型">
          <a-radio-group v-model:value="form.type">
            <a-radio value="docs">文档知识库（上传书籍/资料）</a-radio>
            <a-radio value="persona">个人档案（人设/关系/雷区）</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="form.description" :rows="2" /></a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="分块长度（字符）"><a-input-number v-model:value="form.chunk_size" :min="200" :max="2000" style="width: 100%" /></a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="分块重叠"><a-input-number v-model:value="form.chunk_overlap" :min="0" :max="500" style="width: 100%" /></a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { DatabaseOutlined, DeleteOutlined, PlusOutlined, ProfileOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../api'
import { useSettingsStore } from '../stores/settings'

const kbs = ref([])
const creating = ref(false)
const busy = ref(false)
const form = ref({ name: '', type: 'docs', description: '', chunk_size: 600, chunk_overlap: 100 })
const settingsStore = useSettingsStore()

async function load() {
  kbs.value = await http.get('/kbs')
}
function openCreate() {
  form.value = { name: '', type: 'docs', description: '', chunk_size: settingsStore.settings.chunk_size || 600, chunk_overlap: settingsStore.settings.chunk_overlap || 100 }
  creating.value = true
}
async function create() {
  if (!form.value.name.trim()) return message.warning('请填写名称')
  busy.value = true
  try {
    await http.post('/kbs', form.value)
    creating.value = false
    message.success('已创建')
    await load()
  } finally {
    busy.value = false
  }
}
async function del(kb) {
  await http.delete(`/kbs/${kb.id}`)
  message.success('已删除')
  await load()
}
onMounted(async () => {
  await settingsStore.ensure()
  await load()
})
</script>

<template>
  <div>
    <a-card style="margin-bottom: 16px">
      <a-textarea v-model:value="query" placeholder="输入想检索的内容，例：怎么高情商地拒绝别人的邀请" :rows="3" @pressEnter="doSearch" />
      <div style="margin-top: 12px; display: flex; gap: 16px; align-items: center; flex-wrap: wrap">
        <a-select v-model:value="selectedKbs" mode="multiple" placeholder="全部知识库" style="min-width: 260px" :options="kbOptions" />
        <span>返回条数 <a-input-number v-model:value="topK" :min="2" :max="20" /></span>
        <a-button type="primary" :loading="loading" @click="doSearch"><SearchOutlined /> 检索</a-button>
      </div>
    </a-card>

    <a-empty v-if="searched && !hits.length" description="没有检索到相关内容" />
    <a-card v-for="(h, i) in hits" :key="i" size="small" style="margin-bottom: 12px">
      <template #title>
        <span style="font-size: 13px">
          <a-tag :color="h.kb_type === 'persona' ? 'orange' : 'blue'">{{ h.kb_name }}</a-tag>
          {{ h.metadata.source }}
          <span v-if="h.metadata.chapter" style="color: #8a919f"> · {{ h.metadata.chapter }}</span>
          <span v-if="h.metadata.page" style="color: #8a919f"> · 第 {{ h.metadata.page }} 页</span>
        </span>
      </template>
      <template #extra>
        <a-progress type="circle" :size="28" :percent="Math.round(h.score * 100)" :stroke-width="10" />
      </template>
      <pre class="snippet" style="font-size: 13.5px; line-height: 1.8; max-height: 200px; overflow: auto" v-html="highlight(h.text, query)" />
    </a-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { SearchOutlined } from '@ant-design/icons-vue'
import http from '../api'
import { highlight } from '../utils/format'
import { useSettingsStore } from '../stores/settings'

const query = ref('')
const selectedKbs = ref([])
const topK = ref(6)
const loading = ref(false)
const searched = ref(false)
const hits = ref([])
const kbOptions = ref([])
const settingsStore = useSettingsStore()

async function doSearch() {
  if (!query.value.trim()) return
  loading.value = true
  try {
    const res = await http.post('/search', { query: query.value, kb_ids: selectedKbs.value, top_k: topK.value })
    hits.value = res.hits
    searched.value = true
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await settingsStore.ensure()
  topK.value = settingsStore.settings.top_k || 6
  const kbs = await http.get('/kbs')
  kbOptions.value = kbs.map((k) => ({ value: k.id, label: k.name }))
})
</script>

<template>
  <a-row :gutter="16">
    <a-col :span="14">
      <a-card title="默认参数">
        <a-form layout="vertical" style="max-width: 480px">
          <a-form-item label="生成回复模型（chat model）">
            <a-select v-model:value="form.chat_model" :options="models.map((m) => ({ value: m }))" />
          </a-form-item>
          <a-form-item label="向量模型（embed model，新建知识库时使用）">
            <a-select v-model:value="form.embed_model" :options="models.map((m) => ({ value: m }))" />
          </a-form-item>
          <a-row :gutter="12">
            <a-col :span="12">
              <a-form-item label="分块长度（字符）"><a-input-number v-model:value="form.chunk_size" :min="200" :max="2000" style="width: 100%" /></a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="分块重叠"><a-input-number v-model:value="form.chunk_overlap" :min="0" :max="500" style="width: 100%" /></a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="12">
            <a-col :span="12">
              <a-form-item label="检索条数 top_k"><a-input-number v-model:value="form.top_k" :min="2" :max="20" style="width: 100%" /></a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="生成温度 temperature">
                <a-slider v-model:value="form.temperature" :min="0" :max="1.5" :step="0.1" />
              </a-form-item>
            </a-col>
          </a-row>
          <a-button type="primary" :loading="saving" @click="save">保存设置</a-button>
        </a-form>
      </a-card>
    </a-col>
    <a-col :span="10">
      <a-card title="说明">
        <a-typography>
          <a-typography-paragraph>
            <ul style="padding-left: 18px; margin: 0; line-height: 2">
              <li>修改<b>向量模型</b>只影响之后新建的知识库；已有知识库要换模型请删除重建。</li>
              <li><b>分块</b>决定每次检索召回的文本粒度：书越厚建议分块越小、重叠越大。</li>
              <li><b>top_k</b> 是生成回复时引用的书籍知识条数。</li>
              <li>模型列表来自本机 Ollama，可用 <code>ollama pull qwen3:8b</code> 拉取更强模型后在这里切换。</li>
            </ul>
          </a-typography-paragraph>
        </a-typography>
      </a-card>
    </a-col>
  </a-row>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import http from '../api'
import { useSettingsStore } from '../stores/settings'

const form = ref({})
const models = ref([])
const saving = ref(false)
const settingsStore = useSettingsStore()

async function save() {
  saving.value = true
  try {
    form.value = await settingsStore.save(form.value)
    message.success('已保存')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  form.value = { ...(await settingsStore.ensure()) }
  models.value = (await http.get('/system/models')).models
})
</script>

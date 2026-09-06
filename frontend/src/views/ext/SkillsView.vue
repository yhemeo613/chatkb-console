<template>
  <div>
    <div style="margin-bottom: 14px">
      <a-button type="primary" @click="openCreate"><PlusOutlined /> 新建技能</a-button>
      <span class="page-tip" style="margin-left: 12px">技能 = 关键词匹配 + 场景纪律 + 范例，保存立即生效（热加载）</span>
    </div>
    <a-row :gutter="16">
      <a-col :span="8" v-for="s in skills" :key="s.file" style="margin-bottom: 16px">
        <a-card size="small">
          <template #title>{{ s.name }}</template>
          <template #extra>
            <a-tag v-if="s.builtin" color="default">内置</a-tag>
            <a-space v-else>
              <a @click="openEdit(s)">编辑</a>
              <a-popconfirm title="删除该技能？" @confirm="del(s)"><a style="color: #ff4d4f">删除</a></a-popconfirm>
            </a-space>
          </template>
          <div style="margin-bottom: 8px">
            <a-tag v-for="m in s.match" :key="m">{{ m }}</a-tag>
          </div>
          <p class="page-tip" style="min-height: 40px">{{ s.prompt }}</p>
          <p v-if="s.example" style="font-size: 12px">范例：{{ s.example }}</p>
        </a-card>
      </a-col>
    </a-row>

    <a-modal v-model:open="editing" :title="form.file ? `编辑：${form.file}` : '新建技能'" @ok="save" :width="620">
      <a-form layout="vertical">
        <a-form-item label="技能名" required><a-input v-model:value="form.name" placeholder="例：跨境商务沟通" /></a-form-item>
        <a-form-item label="匹配关键词（输入回车添加）">
          <a-select v-model:value="form.match" mode="tags" placeholder="例：外贸、客户、报关" />
        </a-form-item>
        <a-form-item label="场景纪律（追加给模型）" required>
          <a-textarea v-model:value="form.prompt" :rows="4" />
        </a-form-item>
        <a-form-item label="参考范例"><a-input v-model:value="form.example" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../../api'

const skills = ref([])
const editing = ref(false)
const form = reactive({ file: '', name: '', match: [], prompt: '', example: '' })
const stemOf = (f) => f.replace(/\.json$/, '')

async function load() { skills.value = await http.get('/ext/skills') }
function openCreate() {
  Object.assign(form, { file: '', name: '', match: [], prompt: '', example: '' })
  editing.value = true
}
function openEdit(s) {
  Object.assign(form, { file: s.file, name: s.name, match: s.match || [], prompt: s.prompt || '', example: s.example || '' })
  editing.value = true
}
async function save() {
  if (!form.name.trim()) return message.warning('请填写技能名')
  const stem = form.file ? stemOf(form.file) : form.name.trim()
  await http.post(`/ext/skills/${encodeURIComponent(stem)}`, form)
  message.success('已保存并热加载')
  editing.value = false
  await load()
}
async function del(s) {
  await http.delete(`/ext/skills/${encodeURIComponent(stemOf(s.file))}`)
  message.success('已删除')
  await load()
}
onMounted(load)
</script>

<style lang="less" scoped>
@import '../../styles/variables.less';
</style>

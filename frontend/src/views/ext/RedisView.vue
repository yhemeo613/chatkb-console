<template>
  <a-row :gutter="16">
    <a-col :span="9">
      <a-card title="键扫描" size="small">
        <template #extra>
          <a-tag :color="info.backend === 'redis' ? 'green' : 'orange'">{{ info.backend || '-' }}</a-tag>
        </template>
        <a-input-search v-model:value="pattern" placeholder="chatkb:*" @search="load" />
        <div class="page-tip" style="margin: 8px 0">共 {{ items.length }} 个键（最多展示 200）</div>
        <a-list :data-source="items" size="small" style="max-height: 520px; overflow: auto" row-key="key">
          <template #renderItem="{ item }">
            <a-list-item style="cursor: pointer" :class="{ active: item.key === current }" @click="open(item)">
              <a-list-item-meta>
                <template #title>{{ item.key }}</template>
                <template #description>{{ item.type }} · TTL {{ item.ttl }}s</template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </a-col>
    <a-col :span="15">
      <a-card :title="current || '点击左侧键查看值'" size="small">
        <template #extra>
          <a-popconfirm v-if="current" title="删除该键？" @confirm="del">
            <a style="color: #ff4d4f">删除</a>
          </a-popconfirm>
        </template>
        <pre v-if="value" class="mono" style="font-size: 12px; background: #fafbfc; padding: 12px; border-radius: 6px; max-height: 520px; overflow: auto">{{ value }}</pre>
        <a-empty v-else description="未选择键" />
      </a-card>
    </a-col>
  </a-row>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import http from '../../api'

const pattern = ref('chatkb:*')
const items = ref([])
const current = ref('')
const value = ref('')
const info = ref({})

async function load() {
  const d = await http.get('/ext/redis/keys', { params: { pattern: pattern.value } })
  items.value = d.items
  info.value = { backend: d.backend }
}
async function open(item) {
  current.value = item.key
  const d = await http.get('/ext/redis/key', { params: { key: item.key } })
  value.value = d.kind === 'hash' ? JSON.stringify(d.value, null, 2) : d.value
}
async function del() {
  await http.post('/ext/redis/delete', { keys: [current.value] })
  message.success('已删除')
  current.value = ''; value.value = ''
  await load()
}
onMounted(load)
</script>

<style lang="less" scoped>
@import '../../styles/variables.less';
.active { background: @green-bg; }
</style>

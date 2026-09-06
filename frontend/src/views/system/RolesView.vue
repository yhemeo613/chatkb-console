<template>
  <a-card title="角色管理">
    <template #extra>
      <a-button type="primary" @click="openCreate"><PlusOutlined /> 新增角色</a-button>
    </template>

    <a-table :data-source="roles" :loading="loading" row-key="id" :pagination="false">
      <a-table-column title="角色名" data-index="name" :width="140" />
      <a-table-column title="编码" data-index="code" :width="140" />
      <a-table-column title="描述" data-index="description" />
      <a-table-column title="成员数" data-index="user_count" :width="80" />
      <a-table-column title="类型" :width="90">
        <template #default="{ record }">
          <a-tag :color="record.is_builtin ? 'default' : 'blue'">{{ record.is_builtin ? '内置' : '自定义' }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="操作" :width="130">
        <template #default="{ record }">
          <a-space>
            <a @click="openEdit(record)">授权/编辑</a>
            <a-popconfirm v-if="!record.is_builtin" title="删除该角色？" @confirm="del(record)">
              <a style="color: #ff4d4f">删除</a>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:open="editing" :title="form.id ? `编辑角色：${form.name}` : '新增角色'" @ok="save" :confirm-loading="saving" :width="560">
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="角色名" required><a-input v-model:value="form.name" /></a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="编码" required>
              <a-input v-model:value="form.code" :disabled="!!form.id" placeholder="例：sales" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述"><a-input v-model:value="form.description" /></a-form-item>
        <a-form-item label="菜单与权限（勾选即授予，含按钮级权限）">
          <a-tree
            v-model:checkedKeys="form.menu_ids" checkable :check-strictly="true"
            :tree-data="menuTree" :height="320" style="overflow: auto"
            :field-names="{ children: 'children', title: 'name', key: 'id' }"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../../api'

const roles = ref([])
const menuTree = ref([])
const loading = ref(false)
const editing = ref(false)
const saving = ref(false)
const form = reactive({ id: '', name: '', code: '', description: '', menu_ids: { checked: [] } })

async function load() {
  loading.value = true
  try {
    roles.value = await http.get('/system/roles')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: '', name: '', code: '', description: '', menu_ids: { checked: [] } })
  editing.value = true
}
function openEdit(record) {
  Object.assign(form, {
    id: record.id, name: record.name, code: record.code,
    description: record.description, menu_ids: { checked: [...record.menu_ids] },
  })
  editing.value = true
}

async function save() {
  if (!form.name.trim() || (!form.id && !form.code.trim())) return message.warning('请填写角色名和编码')
  saving.value = true
  try {
    const menu_ids = form.menu_ids?.checked || form.menu_ids || []
    if (form.id) {
      await http.put(`/system/roles/${form.id}`, {
        name: form.name, description: form.description, menu_ids,
      })
    } else {
      await http.post('/system/roles', {
        name: form.name, code: form.code, description: form.description, menu_ids,
      })
    }
    message.success('已保存')
    editing.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function del(record) {
  await http.delete(`/system/roles/${record.id}`)
  message.success('已删除')
  await load()
}

onMounted(async () => {
  await load()
  menuTree.value = await http.get('/system/menus')
})
</script>

<template>
  <a-card title="菜单管理（目录 / 菜单 / 按钮 三级）">
    <template #extra>
      <a-button type="primary" @click="openCreate('')"><PlusOutlined /> 新增顶级菜单</a-button>
    </template>

    <a-table :data-source="tree" row-key="id" :pagination="false" size="middle" default-expand-all-rows>
      <a-table-column title="名称" data-index="name" :width="240" />
      <a-table-column title="类型" :width="90">
        <template #default="{ record }">
          <a-tag :color="{ dir: 'default', menu: 'blue', button: 'green' }[record.type]">
            {{ { dir: '目录', menu: '菜单', button: '按钮' }[record.type] }}
          </a-tag>
        </template>
      </a-table-column>
      <a-table-column title="路由" data-index="path" :width="160" />
      <a-table-column title="权限码" data-index="permCode" :width="160" />
      <a-table-column title="图标" data-index="icon" :width="90" />
      <a-table-column title="排序" data-index="sort" :width="70" />
      <a-table-column title="操作" :width="190">
        <template #default="{ record }">
          <a-space>
            <a v-if="record.type !== 'button'" @click="openCreate(record.id)">加子级</a>
            <a @click="openEdit(record)">编辑</a>
            <a-popconfirm title="删除该菜单？" @confirm="del(record)">
              <a style="color: #ff4d4f">删除</a>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:open="editing" :title="form.id ? '编辑菜单' : '新增菜单'" @ok="save" :confirm-loading="saving">
      <a-form layout="vertical">
        <a-form-item label="父级">
          <a-tree-select
            v-model:value="form.parent_id" :tree-data="parentOptions" placeholder="空 = 顶级"
            :field-names="{ children: 'children', label: 'name', value: 'id' }" allow-clear
          />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="类型" required>
              <a-radio-group v-model:value="form.type">
                <a-radio-button value="dir">目录</a-radio-button>
                <a-radio-button value="menu">菜单</a-radio-button>
                <a-radio-button value="button">按钮</a-radio-button>
              </a-radio-group>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="排序"><a-input-number v-model:value="form.sort" style="width: 100%" /></a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="名称" required><a-input v-model:value="form.name" /></a-form-item>
        <a-form-item v-if="form.type === 'menu'" label="前端路由" required>
          <a-input v-model:value="form.path" placeholder="例：/system/users" />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="权限码" :required="form.type === 'button'">
              <a-input v-model:value="form.perm_code" placeholder="例：sys:user:create" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="图标名"><a-input v-model:value="form.icon" placeholder="例：setting" /></a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import http from '../../api'

const tree = ref([])
const editing = ref(false)
const saving = ref(false)
const form = reactive({ id: '', parent_id: '', name: '', type: 'menu', path: '', icon: '', perm_code: '', sort: 0 })

const parentOptions = computed(() => {
  const conv = (nodes) => nodes
    .filter((n) => n.type !== 'button')
    .map((n) => ({ id: n.id, name: n.name, children: conv(n.children || []) }))
  return conv(tree.value)
})

async function load() {
  tree.value = await http.get('/system/menus')
}

function openCreate(parentId) {
  Object.assign(form, { id: '', parent_id: parentId || '', name: '', type: parentId ? 'menu' : 'dir', path: '', icon: '', perm_code: '', sort: 0 })
  editing.value = true
}
function openEdit(record) {
  Object.assign(form, {
    id: record.id, parent_id: record.parentId, name: record.name, type: record.type,
    path: record.path, icon: record.icon, perm_code: record.permCode, sort: record.sort,
  })
  editing.value = true
}

async function save() {
  if (!form.name.trim()) return message.warning('请填写名称')
  if (form.type === 'button' && !form.perm_code.trim()) return message.warning('按钮必须填权限码')
  if (form.type === 'menu' && !form.path.trim()) return message.warning('菜单必须填前端路由')
  saving.value = true
  try {
    if (form.id) {
      await http.put(`/system/menus/${form.id}`, form)
    } else {
      await http.post('/system/menus', form)
    }
    message.success('已保存，相关用户重新登录后生效')
    editing.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function del(record) {
  await http.delete(`/system/menus/${record.id}`)
  message.success('已删除')
  await load()
}

onMounted(load)
</script>

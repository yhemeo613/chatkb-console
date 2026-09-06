<template>
  <a-card title="账号管理">
    <template #extra>
      <a-space>
        <a-input-search v-model:value="keyword" placeholder="搜索用户名/昵称" style="width: 220px" @search="load(1)" />
        <a-button type="primary" @click="openCreate"><PlusOutlined /> 新增账号</a-button>
      </a-space>
    </template>

    <a-table :data-source="items" :loading="loading" row-key="id" :pagination="pagination" @change="onPage">
      <a-table-column title="用户名" data-index="username" />
      <a-table-column title="昵称" data-index="nickname" />
      <a-table-column title="角色">
        <template #default="{ record }">
          <a-tag v-for="r in record.roles" :key="r.id" color="blue">{{ r.name }}</a-tag>
          <a-tag v-if="record.is_superuser" color="gold">超管</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="状态" :width="90">
        <template #default="{ record }">
          <a-tag v-if="record.is_superuser" color="default">内置</a-tag>
          <a-switch v-else :checked="record.status === 'active'"
                    checked-value="active" unchecked-value="disabled"
                    @change="(v) => toggleStatus(record, v)" />
        </template>
      </a-table-column>
      <a-table-column title="最后登录" :width="150">
        <template #default="{ record }">{{ fmtTime(record.last_login_at) }}</template>
      </a-table-column>
      <a-table-column title="创建时间" :width="150">
        <template #default="{ record }">{{ fmtTime(record.created_at) }}</template>
      </a-table-column>
      <a-table-column title="操作" :width="170">
        <template #default="{ record }">
          <a-space>
            <a @click="openEdit(record)">编辑</a>
            <a-popconfirm title="重置为 Pass1234？" @confirm="resetPwd(record)">
              <a>重置密码</a>
            </a-popconfirm>
            <a-popconfirm v-if="!record.is_superuser" title="删除该账号？" @confirm="del(record)">
              <a style="color: #ff4d4f">删除</a>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:open="editing" :title="form.id ? '编辑账号' : '新增账号'" @ok="save" :confirm-loading="saving">
      <a-form layout="vertical">
        <a-form-item label="用户名">
          <a-input v-model:value="form.username" :disabled="!!form.id" />
        </a-form-item>
        <a-form-item v-if="!form.id" label="初始密码" required>
          <a-input-password v-model:value="form.password" placeholder="至少 6 位" />
        </a-form-item>
        <a-form-item label="昵称"><a-input v-model:value="form.nickname" /></a-form-item>
        <a-form-item label="角色">
          <a-select v-model:value="form.role_ids" mode="multiple"
                    :options="roleOptions" placeholder="不选则无任何权限" />
        </a-form-item>
        <a-form-item v-if="!form.id" label="状态">
          <a-radio-group v-model:value="form.status">
            <a-radio value="active">启用</a-radio>
            <a-radio value="disabled">停用</a-radio>
          </a-radio-group>
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
import { fmtTime } from '../../utils/format'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const items = ref([])
const loading = ref(false)
const keyword = ref('')
const page = ref(1)
const total = ref(0)
const editing = ref(false)
const saving = ref(false)
const roleOptions = ref([])
const form = reactive({ id: '', username: '', password: '', nickname: '', role_ids: [], status: 'active' })

const pagination = computed(() => ({
  current: page.value, total: total.value, pageSize: 20, showTotal: (t) => `共 ${t} 个账号`,
}))
import { computed } from 'vue'

async function load(p = page.value) {
  loading.value = true
  try {
    const d = await http.get('/system/users', { params: { keyword: keyword.value, page: p, size: 20 } })
    items.value = d.items
    total.value = d.total
    page.value = p
  } finally {
    loading.value = false
  }
}
const onPage = (pg) => load(pg.current)

function openCreate() {
  Object.assign(form, { id: '', username: '', password: '', nickname: '', role_ids: [], status: 'active' })
  editing.value = true
}
function openEdit(record) {
  Object.assign(form, {
    id: record.id, username: record.username, password: '',
    nickname: record.nickname, role_ids: record.roles.map((r) => r.id), status: record.status,
  })
  editing.value = true
}

async function save() {
  saving.value = true
  try {
    if (form.id) {
      await http.put(`/system/users/${form.id}`, {
        nickname: form.nickname, role_ids: form.role_ids, status: form.status,
      })
    } else {
      await http.post('/system/users', form)
    }
    message.success('已保存')
    editing.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function toggleStatus(record, v) {
  await http.put(`/system/users/${record.id}`, { status: v })
  message.success(v === 'active' ? '已启用' : '已停用')
  await load()
}

async function resetPwd(record) {
  await http.put(`/system/users/${record.id}/reset-password`, { new_password: 'Pass1234' })
  message.success(`已重置为 Pass1234，请通知 ${record.username} 尽快修改`)
}

async function del(record) {
  await http.delete(`/system/users/${record.id}`)
  message.success('已删除')
  await load()
}

onMounted(async () => {
  await load(1)
  roleOptions.value = (await http.get('/system/roles')).map((r) => ({ value: r.id, label: r.name }))
})
</script>

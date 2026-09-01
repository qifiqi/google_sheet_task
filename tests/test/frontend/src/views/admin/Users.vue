<template>
  <div class="app-page users-page">
    <PageToolbar eyebrow="管理后台" title="用户管理">
      <template #actions>
        <el-button type="primary" @click="openDialog()" v-permission="'user:manage'">新增用户</el-button>
      </template>
    </PageToolbar>

    <DataTableCard
      :data="users"
      :loading="loading"
      :show-pagination="false"
    >
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="mobile" label="手机号" min-width="140" />
      <el-table-column label="角色">
        <template #default="{ row }">
          <div class="user-role-list">
            <el-tag v-for="r in row.roles" :key="r.id">{{ r.name }}</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-switch
            :model-value="row.is_active"
            @change="(value) => handleToggleActive(row, value)"
          />
        </template>
      </el-table-column>
      <el-table-column label="告警值班" width="120">
        <template #default="{ row }">
          <el-switch
            v-if="isDeveloperUser(row)"
            :model-value="row.is_alert_oncall"
            @change="(value) => handleToggleOncall(row, value)"
          />
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="last_login" label="最后登录" width="180" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDialog(row)" v-permission="'user:manage'">编辑</el-button>
          <el-popconfirm title="确定删除？" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button link type="danger" v-permission="'user:manage'">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </DataTableCard>

    <el-dialog v-model="dialogVisible" :title="editingUser ? '编辑用户' : '新增用户'" width="480px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="form.username" :disabled="!!editingUser" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.mobile" placeholder="用于钉钉告警 @" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" :placeholder="editingUser ? '留空不修改' : '请输入密码'" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role_ids" multiple class="full-width">
            <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" />
        </el-form-item>
        <el-form-item v-if="canShowOncallInDialog" label="值班">
          <el-switch v-model="form.is_alert_oncall" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { getUsers, createUser, updateUser, deleteUser, getRoles } from '@/api/auth'
import { ElMessage } from 'element-plus'
import { usePolling } from '@/composables/usePolling'
import PageToolbar from '@/components/PageToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'

const DEV_ROLE_CODES = ['developer']
const users = ref([])
const roles = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingUser = ref(null)
const form = reactive({
  username: '',
  mobile: '',
  password: '',
  role_ids: [],
  is_active: true,
  is_alert_oncall: false,
})
const canShowOncallInDialog = computed(() => form.role_ids.some(roleId => {
  const role = roles.value.find(item => item.id === roleId)
  return role && DEV_ROLE_CODES.includes(role.code)
}))

function isDeveloperUser(user) {
  return (user?.roles || []).some(role => DEV_ROLE_CODES.includes(role.code))
}

async function loadData() {
  loading.value = true
  try {
    const [uRes, rRes] = await Promise.all([getUsers(), getRoles()])
    users.value = uRes.data || uRes.users || []
    roles.value = rRes.data || rRes.roles || []
  } finally {
    loading.value = false
  }
}

function openDialog(user) {
  editingUser.value = user || null
  form.username = user?.username || ''
  form.mobile = user?.mobile || ''
  form.password = ''
  form.role_ids = user?.roles?.map(r => r.id) || []
  form.is_active = user?.is_active ?? true
  form.is_alert_oncall = isDeveloperUser(user) ? (user?.is_alert_oncall ?? false) : false
  dialogVisible.value = true
}

async function handleSave() {
  saving.value = true
  try {
    const payload = {
      ...form,
      is_alert_oncall: canShowOncallInDialog.value ? form.is_alert_oncall : false,
    }
    if (editingUser.value) {
      await updateUser(editingUser.value.id, payload)
    } else {
      await createUser(payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    loadData()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleToggleOncall(row, value) {
  if (!isDeveloperUser(row)) {
    return
  }
  try {
    await updateUser(row.id, { is_alert_oncall: value })
    row.is_alert_oncall = value
    ElMessage.success('值班状态更新成功')
  } catch {
    ElMessage.error('值班状态更新失败')
  }
}

async function handleToggleActive(row, value) {
  try {
    await updateUser(row.id, { is_active: value })
    row.is_active = value
    ElMessage.success('状态更新成功')
  } catch {
    ElMessage.error('状态更新失败')
  }
}

async function handleDelete(id) {
  await deleteUser(id)
  ElMessage.success('删除成功')
  loadData()
}

usePolling(loadData, { interval: 30000 })
</script>

<style scoped>
.user-role-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>

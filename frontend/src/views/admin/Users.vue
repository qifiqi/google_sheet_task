<template>
  <div class="admin-users">
    <PageToolbar eyebrow="管理中心" title="用户管理" description="管理系统用户账户">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon> 创建用户
        </el-button>
      </template>
    </PageToolbar>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>用户列表</span>
          <el-button text type="primary" @click="loadUsers">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
      <el-table :data="users" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip />
        <el-table-column prop="role_name" label="角色" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.role_name === 'admin' ? 'danger' : 'info'">
              {{ row.role_name || row.role || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="175" align="center">
          <template #default="{ row }">
            <span class="cell-time">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" width="175" align="center">
          <template #default="{ row }">
            <span class="cell-time">{{ formatTime(row.last_login_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" size="small" text @click="openEditDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除此用户？" @confirm="handleDelete(row)">
              <template #reference>
                <el-button type="danger" size="small" text @click.stop>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑用户' : '创建用户'"
      width="500px"
      destroy-on-close
    >
      <el-form :model="form" label-width="100px" ref="formRef">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" placeholder="请输入用户名" :disabled="isEdit" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="密码" required>
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-form-item v-if="isEdit" label="新密码">
          <el-input v-model="form.password" type="password" show-password placeholder="留空则不修改" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="form.role_id" placeholder="选择角色" style="width: 100%" v-loading="rolesLoading">
            <el-option
              v-for="role in roles"
              :key="role.id"
              :label="role.name"
              :value="role.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getUsers, createUser, updateUser, deleteUser, getRoles } from '@/api/auth'
import PageToolbar from '@/components/PageToolbar.vue'

const loading = ref(false)
const users = ref([])
const roles = ref([])
const rolesLoading = ref(false)

// Dialog
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const saving = ref(false)
const form = ref({
  id: null,
  username: '',
  email: '',
  password: '',
  role_id: null,
  is_active: true,
})

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

async function loadUsers() {
  loading.value = true
  try {
    const res = await getUsers()
    const data = res?.data || res || {}
    users.value = data.users || data.items || data || []
  } catch {
    users.value = []
  } finally {
    loading.value = false
  }
}

async function loadRoles() {
  rolesLoading.value = true
  try {
    const res = await getRoles()
    const data = res?.data || res || {}
    roles.value = data.roles || data.items || data || []
  } catch {
    roles.value = []
  } finally {
    rolesLoading.value = false
  }
}

function openCreateDialog() {
  isEdit.value = false
  form.value = { id: null, username: '', email: '', password: '', role_id: null, is_active: true }
  dialogVisible.value = true
  loadRoles()
}

function openEditDialog(row) {
  isEdit.value = true
  form.value = {
    id: row.id,
    username: row.username,
    email: row.email || '',
    password: '',
    role_id: row.role_id || row.role?.id || null,
    is_active: row.is_active ?? true,
  }
  dialogVisible.value = true
  loadRoles()
}

async function handleSave() {
  if (!form.value.username) {
    ElMessage.warning('请输入用户名')
    return
  }
  if (!isEdit.value && !form.value.password) {
    ElMessage.warning('请输入密码')
    return
  }

  saving.value = true
  try {
    const payload = {
      username: form.value.username,
      email: form.value.email,
      role_id: form.value.role_id,
      is_active: form.value.is_active,
    }
    if (form.value.password) {
      payload.password = form.value.password
    }

    if (isEdit.value) {
      await updateUser(form.value.id, payload)
      ElMessage.success('用户已更新')
    } else {
      await createUser(payload)
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    loadUsers()
  } catch {
    ElMessage.error(isEdit.value ? '更新失败' : '创建失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await deleteUser(row.id)
    ElMessage.success('已删除')
    loadUsers()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(loadUsers)
</script>

<style lang="scss" scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>

<template>
  <div class="admin-roles">
    <PageToolbar eyebrow="管理中心" title="角色管理" description="管理系统角色和权限">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon> 创建角色
        </el-button>
      </template>
    </PageToolbar>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>角色列表</span>
          <el-button text type="primary" @click="loadRoles">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
      <el-table :data="roles" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="name" label="角色名称" min-width="140" />
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column prop="user_count" label="用户数" width="90" align="center" />
        <el-table-column label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_system ? 'warning' : 'info'" size="small">
              {{ row.is_system ? '系统' : '自定义' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }"><span class="cell-time">{{ formatTime(row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" size="small" text @click.stop="openEditDialog(row)">编辑</el-button>
            <el-popconfirm
              v-if="!row.is_system"
              title="确定删除此角色？"
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button type="danger" size="small" text @click.stop>删除</el-button>
              </template>
            </el-popconfirm>
            <el-tooltip v-else content="系统角色不可删除" placement="top">
              <el-button type="danger" size="small" text disabled @click.stop>删除</el-button>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑角色' : '创建角色'"
      width="650px"
      destroy-on-close
    >
      <el-form :model="form" label-width="100px" ref="formRef">
        <el-form-item label="角色名称" required>
          <el-input v-model="form.name" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="角色描述" />
        </el-form-item>
        <el-form-item label="权限">
          <div class="permissions-container" v-loading="permsLoading">
            <div
              v-for="(perms, group) in groupedPermissions"
              :key="group"
              class="permission-group"
            >
              <div class="permission-group__header">
                <el-checkbox
                  :model-value="isGroupChecked(perms)"
                  :indeterminate="isGroupIndeterminate(perms)"
                  @change="toggleGroup(perms, $event)"
                >
                  <strong>{{ group }}</strong>
                </el-checkbox>
              </div>
              <div class="permission-group__items">
                <el-checkbox
                  v-for="perm in perms"
                  :key="perm.id"
                  :label="perm.id"
                  :model-value="form.permission_ids.includes(perm.id)"
                  @change="togglePermission(perm.id, $event)"
                >
                  {{ perm.name || perm.label }}
                  <span v-if="perm.description" class="perm-desc">{{ perm.description }}</span>
                </el-checkbox>
              </div>
            </div>
          </div>
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
import { ref, computed, onMounted } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getRoles, createRole, updateRole, deleteRole, getPermissions } from '@/api/auth'
import PageToolbar from '@/components/PageToolbar.vue'

const loading = ref(false)
const roles = ref([])
const allPermissions = ref([])
const permsLoading = ref(false)

// Dialog
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const saving = ref(false)
const form = ref({ id: null, name: '', description: '', permission_ids: [] })

const groupedPermissions = computed(() => {
  const groups = {}
  allPermissions.value.forEach(perm => {
    const group = perm.group || perm.module || '其他'
    if (!groups[group]) groups[group] = []
    groups[group].push(perm)
  })
  return groups
})

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

function isGroupChecked(perms) {
  return perms.every(p => form.value.permission_ids.includes(p.id))
}

function isGroupIndeterminate(perms) {
  const count = perms.filter(p => form.value.permission_ids.includes(p.id)).length
  return count > 0 && count < perms.length
}

function toggleGroup(perms, checked) {
  const ids = perms.map(p => p.id)
  if (checked) {
    const newIds = ids.filter(id => !form.value.permission_ids.includes(id))
    form.value.permission_ids = [...form.value.permission_ids, ...newIds]
  } else {
    form.value.permission_ids = form.value.permission_ids.filter(id => !ids.includes(id))
  }
}

function togglePermission(permId, checked) {
  if (checked) {
    if (!form.value.permission_ids.includes(permId)) {
      form.value.permission_ids.push(permId)
    }
  } else {
    form.value.permission_ids = form.value.permission_ids.filter(id => id !== permId)
  }
}

async function loadRoles() {
  loading.value = true
  try {
    const res = await getRoles()
    const data = res?.data || res || {}
    roles.value = data.roles || data.items || data || []
  } catch {
    roles.value = []
  } finally {
    loading.value = false
  }
}

async function loadPermissions() {
  permsLoading.value = true
  try {
    const res = await getPermissions()
    const data = res?.data || res || {}
    allPermissions.value = data.permissions || data.items || data || []
  } catch {
    allPermissions.value = []
  } finally {
    permsLoading.value = false
  }
}

function openCreateDialog() {
  isEdit.value = false
  form.value = { id: null, name: '', description: '', permission_ids: [] }
  dialogVisible.value = true
  loadPermissions()
}

function openEditDialog(row) {
  isEdit.value = true
  form.value = {
    id: row.id,
    name: row.name,
    description: row.description || '',
    permission_ids: row.permission_ids || row.permissions?.map(p => p.id) || [],
  }
  dialogVisible.value = true
  loadPermissions()
}

async function handleSave() {
  if (!form.value.name) {
    ElMessage.warning('请输入角色名称')
    return
  }

  saving.value = true
  try {
    const payload = {
      name: form.value.name,
      description: form.value.description,
      permission_ids: form.value.permission_ids,
    }
    if (isEdit.value) {
      await updateRole(form.value.id, payload)
      ElMessage.success('角色已更新')
    } else {
      await createRole(payload)
      ElMessage.success('角色已创建')
    }
    dialogVisible.value = false
    loadRoles()
  } catch {
    ElMessage.error(isEdit.value ? '更新失败' : '创建失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await deleteRole(row.id)
    ElMessage.success('已删除')
    loadRoles()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(loadRoles)
</script>

<style lang="scss" scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.permissions-container {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  padding: 12px;
  width: 100%;
}

.permission-group {
  margin-bottom: 16px;

  &:last-child {
    margin-bottom: 0;
  }

  &__header {
    padding-bottom: 8px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    margin-bottom: 8px;
  }

  &__items {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 16px;
    padding-left: 16px;
  }
}

.perm-desc {
  font-size: 11px;
  color: var(--app-text-muted);
  margin-left: 4px;
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>

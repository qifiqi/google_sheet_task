<template>
  <div class="app-page">
    <PageToolbar eyebrow="管理后台" title="角色管理">
      <template #actions>
        <el-button type="primary" @click="openDialog()" v-permission="'user:manage'">新增角色</el-button>
      </template>
    </PageToolbar>

    <DataTableCard
      :data="roles"
      :loading="loading"
      :show-pagination="false"
    >
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="角色名称" />
      <el-table-column prop="code" label="编码" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="权限" min-width="240">
        <template #default="{ row }">
          <span v-if="!row.permissions?.length" class="roles-page__muted">未分配</span>
          <template v-else>
            <el-tag
              v-for="p in row.permissions.slice(0, 3)"
              :key="p.id"
              size="small"
              class="roles-page__perm-tag"
            >{{ p.name }}</el-tag>
            <el-tag v-if="row.permissions.length > 3" size="small" type="info" effect="plain" class="roles-page__perm-tag">
              +{{ row.permissions.length - 3 }}
            </el-tag>
            <el-button link type="primary" @click="openPermissionPreview(row)">查看详情</el-button>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="系统内置" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.is_system" type="warning">内置</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDialog(row)" v-permission="'user:manage'">编辑</el-button>
          <el-popconfirm v-if="!row.is_system" title="确定删除？" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button link type="danger" v-permission="'user:manage'">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </DataTableCard>

    <el-dialog v-model="dialogVisible" :title="editingRole ? '编辑角色' : '新增角色'" width="520px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item v-if="!editingRole" label="编码">
          <el-input v-model="form.code" placeholder="例如：operator" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" />
        </el-form-item>
        <el-form-item label="权限">
          <el-select
            v-model="form.permission_ids"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="请选择权限"
            class="full-width"
            :max-collapse-tags="3"
          >
            <el-option-group
              v-for="(perms, group) in groupedPermissions"
              :key="group"
              :label="group"
            >
              <el-option
                v-for="p in perms"
                :key="p.id"
                :label="p.name"
                :value="p.id"
              />
            </el-option-group>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 权限详情预览弹窗（对齐静态版：按 group 分组列出全部权限名/code） -->
    <el-dialog v-model="previewVisible" :title="previewTitle" width="560px">
      <div v-if="!previewGroups.length" class="roles-page__muted">暂无权限</div>
      <template v-else>
        <div v-for="[groupName, perms] in previewGroups" :key="groupName" class="roles-page__perm-group">
          <div class="roles-page__perm-group-name">{{ groupName }} ({{ perms.length }})</div>
          <div class="roles-page__perm-items">
            <el-tag v-for="p in perms" :key="p.id" :title="p.code" size="small" class="roles-page__perm-item">{{ p.name }}</el-tag>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { getRoles, createRole, updateRole, deleteRole, getPermissions } from '@/api/auth'
import { ElMessage } from 'element-plus'
import { usePolling } from '@/composables/usePolling'
import PageToolbar from '@/components/PageToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'

const roles = ref([])
const groupedPermissions = ref({})
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingRole = ref(null)
const form = reactive({ name: '', code: '', description: '', permission_ids: [] })

// 权限详情预览（对齐静态版 openPermissionPreview）
const previewVisible = ref(false)
const previewRole = ref(null)

const previewTitle = computed(() => (previewRole.value ? `${previewRole.value.name} 权限详情` : '权限详情'))

const previewGroups = computed(() => {
  const permissions = previewRole.value?.permissions
  if (!Array.isArray(permissions) || !permissions.length) return []
  const grouped = permissions.reduce((result, permission) => {
    const groupName = permission.group || 'other'
    if (!result[groupName]) result[groupName] = []
    result[groupName].push(permission)
    return result
  }, {})
  return Object.entries(grouped)
})

function openPermissionPreview(role) {
  previewRole.value = role || null
  previewVisible.value = true
}

async function loadData() {
  loading.value = true
  try {
    const [rRes, pRes] = await Promise.all([getRoles(), getPermissions()])
    roles.value = rRes || []
    groupedPermissions.value = pRes || {}
  } finally {
    loading.value = false
  }
}

function openDialog(role) {
  editingRole.value = role || null
  form.name = role?.name || ''
  form.code = role?.code || ''
  form.description = role?.description || ''
  form.permission_ids = role?.permissions?.map(p => p.id) || []
  dialogVisible.value = true
}

async function handleSave() {
  saving.value = true
  try {
    if (editingRole.value) {
      await updateRole(editingRole.value.id, form)
    } else {
      await createRole(form)
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

async function handleDelete(id) {
  await deleteRole(id)
  ElMessage.success('删除成功')
  loadData()
}

usePolling(loadData, { interval: 30000 })
</script>

<style scoped>
.roles-page__muted {
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}

.roles-page__perm-tag {
  margin-right: 6px;
  margin-bottom: 2px;
}

.roles-page__perm-group {
  margin-bottom: 14px;
}

.roles-page__perm-group-name {
  font-weight: 600;
  margin-bottom: 8px;
}

.roles-page__perm-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.roles-page__perm-item {
  max-width: 100%;
}
</style>

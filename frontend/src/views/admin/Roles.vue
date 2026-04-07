<template>
  <div class="app-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">管理后台</div>
        <h2 class="page-title">角色管理</h2>
      </div>
      <div class="page-toolbar__actions">
        <el-button type="primary" @click="openDialog()" v-permission="'user:manage'">新增角色</el-button>
      </div>
    </div>

    <el-table :data="roles" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="角色名称" />
      <el-table-column prop="code" label="编码" />
      <el-table-column prop="description" label="描述" />
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
    </el-table>

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
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import { getRoles, createRole, updateRole, deleteRole, getPermissions } from '@/api/auth'
import { ElMessage } from 'element-plus'

const roles = ref([])
const groupedPermissions = ref({})
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingRole = ref(null)
const form = reactive({ name: '', code: '', description: '', permission_ids: [] })

async function loadData() {
  loading.value = true
  try {
    const [rRes, pRes] = await Promise.all([getRoles(), getPermissions()])
    roles.value = rRes.data || []
    groupedPermissions.value = pRes.data || {}
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

onMounted(loadData)
</script>

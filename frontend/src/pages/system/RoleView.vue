<script setup lang="ts">
import { computed, onMounted, reactive, shallowRef } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SystemPageHeader from '../../components/system/SystemPageHeader.vue'
import { useAdminIdentity } from '../../composables/useAdminIdentity'
import { useAuth } from '../../composables/useAuth'
import type { AdminRole } from '../../types/system'

const auth = useAuth()
const identity = useAdminIdentity()
const keyword = shallowRef('')
const dialogVisible = shallowRef(false)
const previewVisible = shallowRef(false)
const editing = shallowRef<AdminRole | null>(null)
const previewRole = shallowRef<AdminRole | null>(null)
const saving = shallowRef(false)
const form = reactive({ name: '', code: '', description: '', permission_ids: [] as number[] })

const filteredRoles = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return query ? identity.roles.value.filter((role) => `${role.name} ${role.code} ${role.description || ''}`.toLowerCase().includes(query)) : identity.roles.value
})

function canManage() { return auth.hasPermission('user:manage') }
function openCreate() { editing.value = null; Object.assign(form, { name: '', code: '', description: '', permission_ids: [] }); dialogVisible.value = true }
function openEdit(role: AdminRole) { editing.value = role; Object.assign(form, { name: role.name, code: role.code, description: role.description || '', permission_ids: (role.permissions || []).map((permission) => permission.id) }); dialogVisible.value = true }
function openPreview(role: AdminRole) { previewRole.value = role; previewVisible.value = true }

async function save() {
  if (!form.name.trim() || (!editing.value && !form.code.trim())) { ElMessage.warning('请填写角色名称和编码'); return }
  saving.value = true
  try {
    await identity.saveRole({ id: editing.value?.id, name: form.name.trim(), code: form.code.trim(), description: form.description.trim(), permission_ids: [...form.permission_ids] })
    dialogVisible.value = false
    ElMessage.success(editing.value ? '角色已更新' : '角色已创建')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存角色失败') } finally { saving.value = false }
}

async function remove(role: AdminRole) {
  try {
    await ElMessageBox.confirm(`删除角色“${role.name}”后无法恢复，是否继续？`, '删除角色', { type: 'error', confirmButtonText: '删除' })
    await identity.removeRole(role.id)
    ElMessage.success('角色已删除')
  } catch (error) { if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '删除角色失败') }
}

onMounted(identity.loadRolesAndPermissions)
</script>

<template>
  <section class="role-page">
    <SystemPageHeader section="系统模块" title="角色管理"><el-button :icon="Refresh" @click="identity.loadRolesAndPermissions">刷新</el-button><el-button v-if="canManage()" type="primary" :icon="Plus" @click="openCreate">新增角色</el-button></SystemPageHeader>
    <section class="role-page__panel">
      <div class="role-page__toolbar"><el-input v-model="keyword" clearable placeholder="搜索角色名称、编码或说明" /><span>共 {{ filteredRoles.length }} 个角色</span></div>
      <el-alert v-if="identity.errorMessage.value" :title="identity.errorMessage.value" type="error" show-icon :closable="false" />
      <el-table v-loading="identity.loading.value" :data="filteredRoles" empty-text="暂无角色">
        <el-table-column prop="id" label="ID" width="72" />
        <el-table-column prop="name" label="角色名称" min-width="150" />
        <el-table-column prop="code" label="角色编码" min-width="150"><template #default="{ row }"><code>{{ row.code }}</code></template></el-table-column>
        <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
        <el-table-column label="权限" width="128"><template #default="{ row }"><el-button link type="primary" @click="openPreview(row)">{{ row.permissions?.length || 0 }} 项权限</el-button></template></el-table-column>
        <el-table-column label="类型" width="96"><template #default="{ row }"><el-tag :type="row.is_system ? 'warning' : 'info'">{{ row.is_system ? '内置' : '自定义' }}</el-tag></template></el-table-column>
        <el-table-column v-if="canManage()" fixed="right" label="操作" width="128"><template #default="{ row }"><el-button link type="primary" @click="openEdit(row)">编辑</el-button><el-tooltip :disabled="!row.is_system" content="系统内置角色不可删除"><el-button link type="danger" :disabled="row.is_system" @click="remove(row)">删除</el-button></el-tooltip></template></el-table-column>
      </el-table>
    </section>
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑角色' : '新增角色'" width="min(760px, calc(100vw - 32px))" :close-on-click-modal="false">
      <el-form label-position="top" @submit.prevent="save"><div class="role-page__form-grid"><el-form-item label="角色名称" required><el-input v-model="form.name" maxlength="80" /></el-form-item><el-form-item label="角色编码" required><el-input v-model="form.code" :disabled="Boolean(editing)" maxlength="80" /></el-form-item></div><el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit /></el-form-item><el-form-item label="权限"><el-scrollbar class="role-page__permissions-scroll" always :min-size="36"><div class="role-page__permission-groups"><section v-for="(permissions, group) in identity.permissions.value" :key="group" class="role-page__permission-group"><div><strong>{{ group }}</strong><span>{{ permissions.length }} 项</span></div><el-checkbox-group v-model="form.permission_ids"><el-checkbox v-for="permission in permissions" :key="permission.id" :value="permission.id"><span>{{ permission.name }}</span><code>{{ permission.code }}</code></el-checkbox></el-checkbox-group></section></div></el-scrollbar></el-form-item></el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="previewVisible" :title="`${previewRole?.name || ''} 权限详情`" width="min(680px, calc(100vw - 32px))">
      <el-empty v-if="!previewRole?.permissions?.length" description="暂无权限" :image-size="64" />
      <div v-else class="role-page__preview"><el-tag v-for="permission in previewRole.permissions" :key="permission.id" type="info" effect="plain"><el-tooltip :content="permission.code">{{ permission.name }}</el-tooltip></el-tag></div>
    </el-dialog>
  </section>
</template>

<style scoped>
.role-page { display: grid; gap: 16px; }.role-page__panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.role-page__toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }.role-page__toolbar :deep(.el-input) { width: 300px; }.role-page__toolbar > span { margin-left: auto; color: var(--admin-text-muted); font-size: 13px; }.role-page__form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }.role-page__permissions-scroll { height: min(400px, 52vh); width: 100%; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); }.role-page__permission-groups { display: grid; gap: 18px; padding: 16px; }.role-page__permission-group { display: grid; gap: 10px; }.role-page__permission-group > div { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--admin-border-light); padding-bottom: 8px; }.role-page__permission-group strong { color: var(--admin-text); font-size: 14px; }.role-page__permission-group > div span { color: var(--admin-text-muted); font-size: 12px; }.role-page__permission-group :deep(.el-checkbox-group) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 16px; }.role-page__permission-group :deep(.el-checkbox) { height: auto; min-width: 0; margin-right: 0; }.role-page__permission-group :deep(.el-checkbox__label) { display: inline-flex; min-width: 0; flex-direction: column; }.role-page__permission-group code { color: var(--admin-text-muted); font-size: 11px; }.role-page__preview { display: flex; flex-wrap: wrap; gap: 8px; }@media (max-width: 640px) { .role-page__panel { padding: 16px; }.role-page__toolbar :deep(.el-input) { width: 100%; }.role-page__toolbar > span { width: 100%; margin-left: 0; }.role-page__form-grid, .role-page__permission-group :deep(.el-checkbox-group) { grid-template-columns: 1fr; gap: 0; } }
</style>

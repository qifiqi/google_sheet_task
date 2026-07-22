<script setup lang="ts">
import { computed, onMounted, reactive, shallowRef } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SystemPageHeader from '../../components/system/SystemPageHeader.vue'
import { useAdminIdentity } from '../../composables/useAdminIdentity'
import { useAuth } from '../../composables/useAuth'
import { formatDateTime } from '../../utils/format'
import type { AdminUser } from '../../types/system'

const auth = useAuth()
const identity = useAdminIdentity()
const keyword = shallowRef('')
const statusFilter = shallowRef('')
const dialogVisible = shallowRef(false)
const editing = shallowRef<AdminUser | null>(null)
const saving = shallowRef(false)
const form = reactive({ username: '', mobile: '', password: '', role_ids: [] as number[], is_active: true, is_alert_oncall: false })

const filteredUsers = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return identity.users.value.filter((user) => (statusFilter.value === '' || user.is_active === (statusFilter.value === 'true')) && (!query || `${user.username} ${user.mobile || ''} ${(user.roles || []).map((role) => role.name).join(' ')}`.toLowerCase().includes(query)))
})
const canAlertOncall = computed(() => identity.roles.value.some((role) => form.role_ids.includes(role.id) && role.code.toLowerCase() === 'developer'))

function canManage() { return auth.hasPermission('user:manage') }
function isDeveloper(user: AdminUser) { return (user.roles || []).some((role) => role.code.toLowerCase() === 'developer') }
function openCreate() { editing.value = null; Object.assign(form, { username: '', mobile: '', password: '', role_ids: [], is_active: true, is_alert_oncall: false }); dialogVisible.value = true }
function openEdit(user: AdminUser) { editing.value = user; Object.assign(form, { username: user.username, mobile: user.mobile || '', password: '', role_ids: (user.roles || []).map((role) => role.id), is_active: user.is_active, is_alert_oncall: user.is_alert_oncall && isDeveloper(user) }); dialogVisible.value = true }

async function save() {
  if (!form.username.trim() || (!editing.value && !form.password)) { ElMessage.warning('新增用户必须填写用户名和密码'); return }
  if (!form.role_ids.length) { ElMessage.warning('请至少选择一个角色'); return }
  if (form.password && form.password.length < 6) { ElMessage.warning('密码长度不能少于 6 位'); return }
  saving.value = true
  try {
    await identity.saveUser({ id: editing.value?.id, username: form.username.trim(), mobile: form.mobile.trim(), password: form.password || undefined, role_ids: [...form.role_ids], is_active: form.is_active, is_alert_oncall: canAlertOncall.value && form.is_alert_oncall })
    dialogVisible.value = false
    ElMessage.success(editing.value ? '用户已更新' : '用户已创建')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存用户失败') } finally { saving.value = false }
}

async function updateStatus(user: AdminUser, payload: Partial<AdminUser>, label: string) {
  try { await identity.updateUser(user.id, payload); ElMessage.success(`${label}已更新`) } catch (error) { ElMessage.error(error instanceof Error ? error.message : `更新${label}失败`) }
}

async function remove(user: AdminUser) {
  try {
    await ElMessageBox.confirm(`删除用户“${user.username}”后无法恢复，是否继续？`, '删除用户', { type: 'error', confirmButtonText: '删除' })
    await identity.removeUser(user.id)
    ElMessage.success('用户已删除')
  } catch (error) { if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '删除用户失败') }
}

onMounted(identity.loadUsersAndRoles)
</script>

<template>
  <section class="user-page">
    <SystemPageHeader section="系统模块" title="用户管理"><el-button :icon="Refresh" @click="identity.loadUsersAndRoles">刷新</el-button><el-button v-if="canManage()" type="primary" :icon="Plus" @click="openCreate">新增用户</el-button></SystemPageHeader>
    <section class="user-page__panel">
      <div class="user-page__toolbar"><el-input v-model="keyword" clearable placeholder="搜索用户名、手机或角色" /><el-select v-model="statusFilter" clearable placeholder="全部状态"><el-option label="启用" value="true" /><el-option label="禁用" value="false" /></el-select><span>共 {{ filteredUsers.length }} 人</span></div>
      <el-alert v-if="identity.errorMessage.value" :title="identity.errorMessage.value" type="error" show-icon :closable="false" />
      <el-table v-loading="identity.loading.value" :data="filteredUsers" empty-text="暂无用户">
        <el-table-column prop="id" label="ID" width="72" />
        <el-table-column prop="username" label="用户名" min-width="150" />
        <el-table-column label="角色" min-width="220"><template #default="{ row }"><div class="user-page__roles"><el-tag v-for="role in row.roles" :key="role.id" type="info" effect="plain">{{ role.name }}</el-tag><span v-if="!row.roles?.length">-</span></div></template></el-table-column>
        <el-table-column prop="mobile" label="手机号" width="150"><template #default="{ row }">{{ row.mobile || '-' }}</template></el-table-column>
        <el-table-column label="账号状态" width="112"><template #default="{ row }"><el-switch :model-value="row.is_active" :disabled="!canManage()" inline-prompt active-text="启" inactive-text="禁" @change="(value) => updateStatus(row, { is_active: Boolean(value) }, '账号状态')" /></template></el-table-column>
        <el-table-column label="开发者值班" width="120"><template #default="{ row }"><el-switch v-if="isDeveloper(row)" :model-value="row.is_alert_oncall" :disabled="!canManage()" @change="(value) => updateStatus(row, { is_alert_oncall: Boolean(value) }, '值班状态')" /><span v-else>-</span></template></el-table-column>
        <el-table-column label="创建时间" width="180"><template #default="{ row }">{{ formatDateTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="最后登录" width="180"><template #default="{ row }">{{ formatDateTime(row.last_login) }}</template></el-table-column>
        <el-table-column v-if="canManage()" fixed="right" label="操作" width="128"><template #default="{ row }"><el-button link type="primary" @click="openEdit(row)">编辑</el-button><el-button link type="danger" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
    </section>
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '新增用户'" width="min(620px, calc(100vw - 32px))" :close-on-click-modal="false">
      <el-form label-position="top" @submit.prevent="save"><div class="user-page__form-grid"><el-form-item label="用户名" required><el-input v-model="form.username" :disabled="Boolean(editing)" maxlength="80" /></el-form-item><el-form-item :label="editing ? '重置密码' : '登录密码'" :required="!editing"><el-input v-model="form.password" type="password" show-password :placeholder="editing ? '留空表示不修改' : '至少 6 位'" /></el-form-item></div><el-form-item label="手机号"><el-input v-model="form.mobile" maxlength="30" /></el-form-item><el-form-item label="角色" required><el-select v-model="form.role_ids" multiple collapse-tags collapse-tags-tooltip><el-option v-for="role in identity.roles.value" :key="role.id" :label="role.name" :value="role.id" /></el-select></el-form-item><div class="user-page__switches"><el-switch v-model="form.is_active" active-text="账号启用" /><el-tooltip :disabled="canAlertOncall" content="仅 developer 角色可参与值班"><el-switch v-model="form.is_alert_oncall" :disabled="!canAlertOncall" active-text="开发者值班" /></el-tooltip></div></el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.user-page { display: grid; gap: 16px; }.user-page__panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.user-page__toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }.user-page__toolbar :deep(.el-input) { width: 280px; }.user-page__toolbar :deep(.el-select) { width: 160px; }.user-page__toolbar span { margin-left: auto; color: var(--admin-text-muted); font-size: 13px; }.user-page__roles, .user-page__switches { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }.user-page__roles span { color: var(--admin-text-muted); }.user-page__form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }.user-page__switches { gap: 24px; }@media (max-width: 640px) { .user-page__panel { padding: 16px; }.user-page__toolbar :deep(.el-input), .user-page__toolbar :deep(.el-select) { width: 100%; }.user-page__toolbar span { width: 100%; margin-left: 0; }.user-page__form-grid { grid-template-columns: 1fr; gap: 0; } }
</style>

<script setup lang="ts">
import { computed, onMounted, reactive, shallowRef } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SystemPageHeader from '../../components/system/SystemPageHeader.vue'
import { useAuthStore } from '../../stores/auth'
import { useNavigationStore } from '../../stores/navigation'
import { useNavigationRegistry } from '../../composables/useNavigationRegistry'
import type { NavigationRegistryItem } from '../../types/system'

const auth = useAuthStore()
const navigation = useNavigationStore()
const registry = useNavigationRegistry()
const keyword = shallowRef('')
const visibleFilter = shallowRef('')
const dialogVisible = shallowRef(false)
const editing = shallowRef<NavigationRegistryItem | null>(null)
const saving = shallowRef(false)
const form = reactive({ label: '', key: '', path: '', permission: '', parent_key: '', sort_order: 0, is_visible: false })

const parentOptions = computed(() => registry.items.value.filter((item) => !item.path && item.id !== editing.value?.id))
const parentNames = computed(() => new Map(registry.items.value.map((item) => [item.key, item.label])))
const filteredItems = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return registry.items.value.filter((item) => (visibleFilter.value === '' || item.is_visible === (visibleFilter.value === 'true')) && (!query || `${item.label} ${item.key} ${item.path || ''} ${item.permission || ''}`.toLowerCase().includes(query)))
})

function canManage() { return auth.hasPermission('navigation:manage') }
function openCreate() { editing.value = null; Object.assign(form, { label: '', key: '', path: '', permission: '', parent_key: '', sort_order: 0, is_visible: false }); dialogVisible.value = true }
function openEdit(item: NavigationRegistryItem) { editing.value = item; Object.assign(form, { label: item.label, key: item.key, path: item.path || '', permission: item.permission || '', parent_key: item.parent_key || '', sort_order: item.sort_order, is_visible: item.is_visible }); dialogVisible.value = true }

async function save() {
  if (!form.label.trim() || !form.key.trim()) { ElMessage.warning('请填写菜单名称和路由 Key'); return }
  if (form.is_visible && form.path.trim() && !form.permission.trim()) { ElMessage.warning('可见页面路由必须填写权限码'); return }
  saving.value = true
  try {
    await registry.save({ id: editing.value?.id, label: form.label.trim(), key: form.key.trim(), path: form.path.trim() || null, permission: form.permission.trim() || null, parent_key: form.parent_key || null, sort_order: form.sort_order, is_visible: form.is_visible })
    dialogVisible.value = false
    await navigation.loadNavigation()
    ElMessage.success(editing.value ? '路由已更新' : '路由已创建')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存路由失败') } finally { saving.value = false }
}

async function remove(item: NavigationRegistryItem) {
  try {
    await ElMessageBox.confirm(`删除路由“${item.label}”后无法恢复，是否继续？`, '删除路由', { type: 'error', confirmButtonText: '删除' })
    await registry.remove(item.id)
    await navigation.loadNavigation()
    ElMessage.success('路由已删除')
  } catch (error) { if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '删除路由失败') }
}

onMounted(registry.load)
</script>

<template>
  <section class="navigation-page">
    <SystemPageHeader section="系统模块" title="路由表管理"><el-button :icon="Refresh" @click="registry.load">刷新</el-button><el-button v-if="canManage()" type="primary" :icon="Plus" @click="openCreate">新增路由</el-button></SystemPageHeader>
    <section class="navigation-page__panel">
      <div class="navigation-page__toolbar"><el-input v-model="keyword" clearable placeholder="搜索名称、Key、路径或权限" /><el-select v-model="visibleFilter" clearable placeholder="全部显示状态"><el-option label="显示" value="true" /><el-option label="隐藏" value="false" /></el-select><span>共 {{ filteredItems.length }} 条</span></div>
      <el-alert v-if="registry.errorMessage.value" :title="registry.errorMessage.value" type="error" show-icon :closable="false" />
      <el-table v-loading="registry.loading.value" :data="filteredItems" row-key="id" empty-text="暂无路由记录">
        <el-table-column prop="id" label="ID" width="72" />
        <el-table-column prop="label" label="菜单名称" min-width="150" />
        <el-table-column prop="key" label="Key" min-width="150"><template #default="{ row }"><code>{{ row.key }}</code></template></el-table-column>
        <el-table-column prop="path" label="路径" min-width="210"><template #default="{ row }"><code>{{ row.path || '-' }}</code></template></el-table-column>
        <el-table-column prop="permission" label="权限码" min-width="210"><template #default="{ row }"><code>{{ row.permission || '-' }}</code></template></el-table-column>
        <el-table-column label="父级" width="140"><template #default="{ row }">{{ parentNames.get(row.parent_key) || '-' }}</template></el-table-column>
        <el-table-column prop="sort_order" label="排序" width="86" align="right" />
        <el-table-column label="显示" width="86"><template #default="{ row }"><el-tag :type="row.is_visible ? 'success' : 'info'">{{ row.is_visible ? '显示' : '隐藏' }}</el-tag></template></el-table-column>
        <el-table-column v-if="canManage()" fixed="right" label="操作" width="128"><template #default="{ row }"><el-button link type="primary" @click="openEdit(row)">编辑</el-button><el-button link type="danger" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
    </section>
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑路由' : '新增路由'" width="min(680px, calc(100vw - 32px))" :close-on-click-modal="false">
      <el-form label-position="top" @submit.prevent="save"><div class="navigation-page__form-grid"><el-form-item label="菜单名称" required><el-input v-model="form.label" maxlength="100" /></el-form-item><el-form-item label="路由 Key" required><el-input v-model="form.key" maxlength="100" /></el-form-item></div><el-form-item label="前端路径"><el-input v-model="form.path" placeholder="分组菜单可留空" /></el-form-item><el-form-item label="权限码"><el-input v-model="form.permission" placeholder="例如 page:admin:users" /></el-form-item><div class="navigation-page__form-grid"><el-form-item label="父级菜单"><el-select v-model="form.parent_key" clearable placeholder="顶级菜单"><el-option v-for="item in parentOptions" :key="item.key" :label="item.label" :value="item.key" /></el-select></el-form-item><el-form-item label="排序"><el-input-number v-model="form.sort_order" :min="0" /></el-form-item></div><el-form-item><el-switch v-model="form.is_visible" active-text="侧边栏显示" inactive-text="侧边栏隐藏" /></el-form-item></el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.navigation-page { display: grid; gap: 16px; }.navigation-page__panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.navigation-page__toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }.navigation-page__toolbar :deep(.el-input) { width: 300px; }.navigation-page__toolbar :deep(.el-select) { width: 170px; }.navigation-page__toolbar span { margin-left: auto; color: var(--admin-text-muted); font-size: 13px; }.navigation-page__form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }@media (max-width: 640px) { .navigation-page__panel { padding: 16px; }.navigation-page__toolbar :deep(.el-input), .navigation-page__toolbar :deep(.el-select) { width: 100%; }.navigation-page__toolbar span { width: 100%; margin-left: 0; }.navigation-page__form-grid { grid-template-columns: 1fr; gap: 0; } }
</style>

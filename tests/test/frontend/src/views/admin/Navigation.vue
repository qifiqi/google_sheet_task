<template>
  <div class="app-page navigation-page">
    <PageToolbar eyebrow="管理后台" title="导航菜单管理">
      <template #actions>
        <el-button type="primary" @click="openDialog()">添加菜单项</el-button>
      </template>
    </PageToolbar>

    <FilterToolbar
      v-model="filters"
      :filters="filterConfig"
      @search="loadData"
      @clear="clearFilters"
    />

    <DataTableCard
      :data="filteredItems"
      :loading="loading"
      :show-pagination="false"
    >
      <el-table-column prop="label" label="名称" min-width="120" />
      <el-table-column prop="key" label="Key" min-width="120">
        <template #default="{ row }">
          <code class="mono-inline">{{ row.key }}</code>
        </template>
      </el-table-column>
      <el-table-column prop="path" label="路径" min-width="140" show-overflow-tooltip />
      <el-table-column prop="permission" label="权限" min-width="120" show-overflow-tooltip />
      <el-table-column prop="parent_key" label="父级Key" width="120">
        <template #default="{ row }">
          {{ row.parent_key || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="sort_order" label="排序" width="80" />
      <el-table-column label="可见" width="80">
        <template #default="{ row }">
          <el-switch
            :model-value="row.is_visible"
            @change="(val) => handleToggleVisible(row, val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确定删除该菜单项？" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button link type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </DataTableCard>
    <el-dialog v-model="dialogVisible" :title="editingItem ? '编辑菜单项' : '添加菜单项'" width="520px" :fullscreen="isMobile">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.label" placeholder="菜单显示名称" />
        </el-form-item>
        <el-form-item label="Key">
          <el-input v-model="form.key" placeholder="唯一标识，如 admin.users" />
        </el-form-item>
        <el-form-item label="路径">
          <el-input v-model="form.path" placeholder="路由路径，如 /admin/users" />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" placeholder="图标名称（可选）" />
        </el-form-item>
        <el-form-item label="权限">
          <el-input v-model="form.permission" placeholder="所需权限，如 user:view" />
        </el-form-item>
        <el-form-item label="父级">
          <el-select v-model="form.parent_key" clearable placeholder="无（顶级菜单）" class="full-width">
            <el-option
              v-for="item in parentOptions"
              :key="item.key"
              :label="item.label"
              :value="item.key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item label="可见">
          <el-switch v-model="form.is_visible" />
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
import { ElMessage } from 'element-plus'
import { getNavigationItems, createNavigationItem, updateNavigationItem, deleteNavigationItem } from '@/api/meta'
import { useResponsive } from '@/composables/useResponsive'
import { usePolling } from '@/composables/usePolling'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'

const { isMobile } = useResponsive()
const items = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingItem = ref(null)

const filters = reactive({ keyword: '', parent: '', visibility: '' })
const form = reactive({
  label: '',
  key: '',
  path: '',
  icon: '',
  permission: '',
  parent_key: '',
  sort_order: 0,
  is_visible: true,
})

const parentOptions = computed(() => {
  return items.value.filter(item => !item.parent_key)
})

const filterConfig = computed(() => [
  { key: 'keyword', type: 'input', placeholder: '名称 / Key / 路径', span: { xs: 24, sm: 8, md: 5 } },
  {
    key: 'parent', type: 'select', placeholder: '父级菜单',
    options: parentOptions.value.map(p => ({ value: p.key, label: p.label })),
    span: { xs: 12, sm: 5, md: 4 },
  },
  {
    key: 'visibility', type: 'select', placeholder: '可见性',
    options: [{ value: '1', label: '可见' }, { value: '0', label: '隐藏' }],
    span: { xs: 12, sm: 4, md: 3 },
  },
])

const filteredItems = computed(() => {
  return items.value.filter(item => {
    const kw = filters.keyword.toLowerCase()
    const matchKw = !kw ||
      (item.label || '').toLowerCase().includes(kw) ||
      (item.key || '').toLowerCase().includes(kw) ||
      (item.path || '').toLowerCase().includes(kw)
    const matchParent = !filters.parent || item.parent_key === filters.parent
    const matchVisibility = filters.visibility === '' ||
      String(Number(!!item.is_visible)) === filters.visibility
    return matchKw && matchParent && matchVisibility
  })
})

function clearFilters() {
  filters.keyword = ''
  filters.parent = ''
  filters.visibility = ''
}

async function loadData() {
  loading.value = true
  try {
    const res = await getNavigationItems()
    items.value = res.data || res.items || []
  } finally {
    loading.value = false
  }
}

function openDialog(item) {
  editingItem.value = item || null
  form.label = item?.label || ''
  form.key = item?.key || ''
  form.path = item?.path || ''
  form.icon = item?.icon || ''
  form.permission = item?.permission || ''
  form.parent_key = item?.parent_key || ''
  form.sort_order = item?.sort_order ?? 0
  form.is_visible = item?.is_visible ?? true
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.key || !form.label) {
    ElMessage.warning('名称和 Key 为必填项')
    return
  }
  saving.value = true
  try {
    const payload = { ...form }
    if (editingItem.value) {
      await updateNavigationItem(editingItem.value.id, payload)
    } else {
      await createNavigationItem(payload)
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

async function handleToggleVisible(row, value) {
  try {
    await updateNavigationItem(row.id, { is_visible: value })
    row.is_visible = value
    ElMessage.success('更新成功')
  } catch {
    ElMessage.error('更新失败')
  }
}

async function handleDelete(id) {
  try {
    await deleteNavigationItem(id)
    ElMessage.success('删除成功')
    loadData()
  } catch {
    ElMessage.error('删除失败')
  }
}

usePolling(loadData, { interval: 30000 })
</script>

<style scoped>
.navigation-page :deep(.el-dialog__body) {
  padding-top: 12px;
}
</style>

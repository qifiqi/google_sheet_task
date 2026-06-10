<template>
  <div class="admin-navigation">
    <PageToolbar eyebrow="管理中心" title="导航管理" description="管理侧边栏导航菜单">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog()">
          <el-icon><Plus /></el-icon> 创建菜单项
        </el-button>
      </template>
    </PageToolbar>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>菜单结构</span>
          <el-button text type="primary" @click="loadNavItems">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
      <el-table
        :data="treeData"
        v-loading="loading"
        row-key="id"
        :tree-props="{ children: 'children' }"
        border
        default-expand-all
        style="width: 100%"
      >
        <el-table-column prop="label" label="显示名称" min-width="180" />
        <el-table-column prop="key" label="菜单键" min-width="140" show-overflow-tooltip />
        <el-table-column prop="path" label="路由路径" min-width="180" show-overflow-tooltip />
        <el-table-column prop="permission" label="权限" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="row.permission" size="small">{{ row.permission }}</el-tag>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="80" align="center" />
        <el-table-column label="可见" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.visible !== false ? 'success' : 'info'" size="small">
              {{ row.visible !== false ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="success" size="small" text @click="openCreateDialog(row.id)">
              子项
            </el-button>
            <el-button type="primary" size="small" text @click="openEditDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除此菜单项？子项也会被删除。" @confirm="handleDelete(row)">
              <template #reference>
                <el-button type="danger" size="small" text>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑菜单项' : '创建菜单项'"
      width="550px"
      destroy-on-close
    >
      <el-form :model="form" label-width="100px" ref="formRef">
        <el-form-item label="菜单键" required>
          <el-input v-model="form.key" placeholder="唯一标识，如 dashboard" />
        </el-form-item>
        <el-form-item label="显示名称" required>
          <el-input v-model="form.label" placeholder="菜单显示名称" />
        </el-form-item>
        <el-form-item label="路由路径">
          <el-input v-model="form.path" placeholder="如 /admin/dashboard" />
        </el-form-item>
        <el-form-item label="权限">
          <el-input v-model="form.permission" placeholder="如 admin:dashboard:view" />
        </el-form-item>
        <el-form-item label="父级菜单">
          <el-select v-model="form.parent_id" placeholder="无（顶级菜单）" clearable style="width: 100%">
            <el-option
              v-for="item in parentOptions"
              :key="item.id"
              :label="item.label"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" placeholder="Element Plus 图标名称" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
        </el-form-item>
        <el-form-item label="可见">
          <el-switch v-model="form.visible" />
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
import { getNavigationItems, createNavigationItem, updateNavigationItem, deleteNavigationItem } from '@/api/meta'
import PageToolbar from '@/components/PageToolbar.vue'

const loading = ref(false)
const navItems = ref([])

// Dialog
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const saving = ref(false)
const form = ref({
  id: null,
  key: '',
  label: '',
  path: '',
  permission: '',
  parent_id: null,
  icon: '',
  sort_order: 0,
  visible: true,
})

const treeData = computed(() => {
  return buildTree(navItems.value)
})

const parentOptions = computed(() => {
  return flattenForOptions(navItems.value)
})

function buildTree(items) {
  const map = {}
  const roots = []
  items.forEach(item => {
    map[item.id] = { ...item, children: [] }
  })
  items.forEach(item => {
    if (item.parent_id && map[item.parent_id]) {
      map[item.parent_id].children.push(map[item.id])
    } else {
      roots.push(map[item.id])
    }
  })
  // Sort by sort_order
  const sortChildren = (nodes) => {
    nodes.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
    nodes.forEach(n => { if (n.children.length) sortChildren(n.children) })
  }
  sortChildren(roots)
  return roots
}

function flattenForOptions(items, depth = 0) {
  const result = []
  const tree = buildTree(items)
  function walk(nodes, level) {
    nodes.forEach(node => {
      result.push({
        id: node.id,
        label: `${' '.repeat(level)}${node.label}`,
      })
      if (node.children?.length) {
        walk(node.children, level + 1)
      }
    })
  }
  walk(tree, 0)
  return result
}

async function loadNavItems() {
  loading.value = true
  try {
    const res = await getNavigationItems()
    const data = res?.data || res || {}
    navItems.value = data.items || data.nav_items || data || []
    if (!Array.isArray(navItems.value)) navItems.value = []
  } catch {
    navItems.value = []
  } finally {
    loading.value = false
  }
}

function openCreateDialog(parentId = null) {
  isEdit.value = false
  form.value = {
    id: null,
    key: '',
    label: '',
    path: '',
    permission: '',
    parent_id: parentId,
    icon: '',
    sort_order: 0,
    visible: true,
  }
  dialogVisible.value = true
}

function openEditDialog(row) {
  isEdit.value = true
  form.value = {
    id: row.id,
    key: row.key,
    label: row.label,
    path: row.path || '',
    permission: row.permission || '',
    parent_id: row.parent_id || null,
    icon: row.icon || '',
    sort_order: row.sort_order ?? 0,
    visible: row.visible !== false,
  }
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.value.key || !form.value.label) {
    ElMessage.warning('请填写菜单键和显示名称')
    return
  }

  saving.value = true
  try {
    const payload = {
      key: form.value.key,
      label: form.value.label,
      path: form.value.path,
      permission: form.value.permission,
      parent_id: form.value.parent_id || null,
      icon: form.value.icon,
      sort_order: form.value.sort_order,
      visible: form.value.visible,
    }
    if (isEdit.value) {
      await updateNavigationItem(form.value.id, payload)
      ElMessage.success('菜单项已更新')
    } else {
      await createNavigationItem(payload)
      ElMessage.success('菜单项已创建')
    }
    dialogVisible.value = false
    loadNavItems()
  } catch {
    ElMessage.error(isEdit.value ? '更新失败' : '创建失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await deleteNavigationItem(row.id)
    ElMessage.success('已删除')
    loadNavItems()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(loadNavItems)
</script>

<style lang="scss" scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.text-muted {
  color: var(--app-text-muted);
}
</style>

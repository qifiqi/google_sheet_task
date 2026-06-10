<template>
  <div class="admin-tasks">
    <PageToolbar eyebrow="管理中心" title="任务管理" description="查看和管理所有任务">
      <template #actions>
        <el-button type="primary" @click="showCreateDialog = true">
          <el-icon><Plus /></el-icon> 创建任务
        </el-button>
      </template>
    </PageToolbar>

    <FilterToolbar
      :filters="FILTERS"
      v-model="filterValues"
      @search="loadTasks"
      @clear="clearFilters"
      class="mb-3"
    />

    <el-table :data="tasks" v-loading="loading" stripe style="width: 100%">
      <el-table-column prop="task_name" label="任务名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="task_type" label="类型" width="130" align="center">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.task_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <StatusTag :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="进度" width="160">
        <template #default="{ row }">
          <TaskProgressCell :current="row.current_step" :total="row.total_steps" />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="175" align="center">
        <template #default="{ row }">
          <span class="cell-time">{{ formatTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'running' || row.status === 'pending'"
            type="warning"
            size="small"
            text
            @click.stop="handleCancel(row)"
          >取消</el-button>
          <el-button
            v-if="row.status === 'error' || row.status === 'cancelled'"
            type="primary"
            size="small"
            text
            @click.stop="handleRestart(row)"
          >重启</el-button>
          <el-button type="info" size="small" text @click.stop="openEditConfig(row)">配置</el-button>
          <el-popconfirm title="确定删除此任务？" @confirm="handleDelete(row)">
            <template #reference>
              <el-button type="danger" size="small" text @click.stop>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadTasks"
        @current-change="loadTasks"
      />
    </div>

    <!-- Edit Config Dialog -->
    <el-dialog v-model="configDialogVisible" title="编辑任务配置" width="600px" destroy-on-close>
      <el-form :model="editConfigForm" label-width="120px" v-if="editConfigForm">
        <el-form-item label="任务名称">
          <el-input v-model="editConfigForm.task_name" disabled />
        </el-form-item>
        <el-form-item label="配置 (JSON)">
          <el-input
            v-model="editConfigForm.config_json"
            type="textarea"
            :rows="12"
            placeholder="请输入 JSON 配置"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingConfig" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- Create Task Dialog -->
    <el-dialog v-model="showCreateDialog" title="创建任务" width="600px" destroy-on-close>
      <el-form :model="createForm" label-width="120px">
        <el-form-item label="任务名称" required>
          <el-input v-model="createForm.task_name" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="任务类型" required>
          <el-select v-model="createForm.task_type" placeholder="选择类型" style="width: 100%">
            <el-option label="C3 参数校验" value="c3" />
            <el-option label="C4 参数校验" value="c4" />
            <el-option label="C5 参数校验" value="c5" />
            <el-option label="回测训练" value="backtest_training" />
            <el-option label="多品种回测" value="backtest_multi" />
          </el-select>
        </el-form-item>
        <el-form-item label="配置 (JSON)">
          <el-input
            v-model="createForm.config_json"
            type="textarea"
            :rows="10"
            placeholder="请输入 JSON 配置（可选）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTasks, createTask, deleteTask, cancelTask, restartTask, updateTaskConfig } from '@/api/task'
import { usePolling } from '@/composables/usePolling'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import StatusTag from '@/components/StatusTag.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'

const loading = ref(false)
const tasks = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const filterValues = ref({ status: '', task_type: '', search: '' })

const FILTERS = [
  {
    key: 'status', type: 'select', label: '状态',
    options: [
      { label: '全部', value: '' },
      { label: '待执行', value: 'pending' },
      { label: '运行中', value: 'running' },
      { label: '已完成', value: 'completed' },
      { label: '错误', value: 'error' },
      { label: '已取消', value: 'cancelled' },
    ],
  },
  {
    key: 'task_type', type: 'select', label: '类型',
    options: [
      { label: '全部', value: '' },
      { label: 'C3', value: 'c3' },
      { label: 'C4', value: 'c4' },
      { label: 'C5', value: 'c5' },
      { label: '回测训练', value: 'backtest_training' },
      { label: '多品种回测', value: 'backtest_multi' },
    ],
  },
  { key: 'search', type: 'input', label: '搜索', placeholder: '任务名称 / ID' },
]

// Config dialog
const configDialogVisible = ref(false)
const editConfigForm = ref(null)
const savingConfig = ref(false)

// Create dialog
const showCreateDialog = ref(false)
const createForm = ref({ task_name: '', task_type: '', config_json: '' })
const creating = ref(false)

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

function clearFilters() {
  filterValues.value = { status: '', task_type: '', search: '' }
  page.value = 1
  loadTasks()
}

async function loadTasks() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      per_page: pageSize.value,
      ...filterValues.value,
    }
    Object.keys(params).forEach(k => { if (!params[k]) delete params[k] })
    const res = await getTasks(params)
    const data = res?.data || res || {}
    tasks.value = data.tasks || data.items || data || []
    total.value = data.total || tasks.value.length
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

async function handleCancel(row) {
  try {
    await ElMessageBox.confirm('确定取消此任务？', '确认')
    await cancelTask(row.id)
    ElMessage.success('任务已取消')
    loadTasks()
  } catch { /* cancelled */ }
}

async function handleRestart(row) {
  try {
    await restartTask(row.id)
    ElMessage.success('任务已重启')
    loadTasks()
  } catch {
    ElMessage.error('重启失败')
  }
}

async function handleDelete(row) {
  try {
    await deleteTask(row.id)
    ElMessage.success('已删除')
    loadTasks()
  } catch {
    ElMessage.error('删除失败')
  }
}

function openEditConfig(row) {
  editConfigForm.value = {
    id: row.id,
    task_name: row.task_name,
    config_json: typeof row.config === 'string' ? row.config : JSON.stringify(row.config || {}, null, 2),
  }
  configDialogVisible.value = true
}

async function saveConfig() {
  savingConfig.value = true
  try {
    let config = editConfigForm.value.config_json
    try {
      config = JSON.parse(config)
    } catch {
      ElMessage.warning('配置 JSON 格式无效')
      return
    }
    await updateTaskConfig(editConfigForm.value.id, { config })
    ElMessage.success('配置已更新')
    configDialogVisible.value = false
    loadTasks()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingConfig.value = false
  }
}

async function handleCreate() {
  if (!createForm.value.task_name || !createForm.value.task_type) {
    ElMessage.warning('请填写任务名称和类型')
    return
  }
  creating.value = true
  try {
    const payload = {
      task_name: createForm.value.task_name,
      task_type: createForm.value.task_type,
    }
    if (createForm.value.config_json) {
      try {
        payload.config = JSON.parse(createForm.value.config_json)
      } catch {
        ElMessage.warning('配置 JSON 格式无效')
        return
      }
    }
    await createTask(payload)
    ElMessage.success('任务已创建')
    showCreateDialog.value = false
    createForm.value = { task_name: '', task_type: '', config_json: '' }
    loadTasks()
  } catch {
    ElMessage.error('创建失败')
  } finally {
    creating.value = false
  }
}

usePolling(loadTasks, { interval: 15000 })
onMounted(loadTasks)
</script>

<style lang="scss" scoped>
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.mb-3 {
  margin-bottom: 12px;
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>

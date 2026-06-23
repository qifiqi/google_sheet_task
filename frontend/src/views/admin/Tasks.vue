<template>
  <div class="app-page admin-tasks-page">
    <PageToolbar eyebrow="管理后台" title="任务管理">
      <template #actions>
        <el-button type="primary" :size="componentSize" @click="openCreate">创建任务</el-button>
      </template>
    </PageToolbar>

    <FilterToolbar
      :filters="filterConfig"
      v-model="filters"
      @search="doFilter"
      @clear="clearFilters"
    />

    <DataTableCard
      title="任务列表"
      :loading="loading"
      :data="tasks"
      :total="total"
      v-model:page="page"
      v-model:page-size="pageSize"
      :pageSizes="[10, 20, 50, 100]"
      @page-change="loadTasks"
    >
      <el-table-column label="任务" min-width="160">
        <template #default="{ row }">
          <div style="font-weight:600">{{ row.name }}</div>
          <div class="admin-tasks-page__sub-id">{{ row.id?.slice(0,8) }}...</div>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="130">
        <template #default="{ row }"><el-tag size="small" type="info">{{ row.task_type }}</el-tag></template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }"><StatusTag :status="row.status" /></template>
      </el-table-column>
      <el-table-column label="参数组" width="70">
        <template #default="{ row }">{{ row.config?.parameters?.length ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="进度" min-width="140">
        <template #default="{ row }">
          <TaskProgressCell :current-step="row.current_step || 0" :total-steps="row.total_steps || 0" />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="160" show-overflow-tooltip />
      <el-table-column prop="start_time" label="开始时间" width="160" show-overflow-tooltip />
      <el-table-column prop="end_time" label="结束时间" width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button link type="primary" @click="$router.push(`/task/${row.id}`)">详情</el-button>
          <el-button link type="info" @click="showDetail(row.id)">摘要</el-button>
          <el-button v-if="row.status === 'running'" link type="warning" @click="handleCancel(row.id)">停止</el-button>
          <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </DataTableCard>

    <!-- 任务摘要抽屉 -->
    <el-drawer v-model="detailDrawerVisible" title="任务摘要" :size="drawerSize">
      <div v-if="detailTask" v-loading="detailLoading">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="任务ID">{{ detailTask.id }}</el-descriptions-item>
          <el-descriptions-item label="任务名称">{{ detailTask.name }}</el-descriptions-item>
          <el-descriptions-item label="任务类型">{{ detailTask.task_type }}</el-descriptions-item>
          <el-descriptions-item label="状态"><StatusTag :status="detailTask.status" /></el-descriptions-item>
          <el-descriptions-item label="进度">{{ detailTask.current_step || 0 }}/{{ detailTask.total_steps || 0 }} ({{ detailTask.progress_percentage || 0 }}%)</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ detailTask.duration_seconds != null ? detailTask.duration_seconds + 's' : '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detailTask.created_at }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ detailTask.start_time }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ detailTask.end_time }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top:16px">
          <h4>任务配置</h4>
          <CodeBlock :content="detailTask.config || {}" />
        </div>
        <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
          <el-button type="primary" @click="$router.push(`/task/${detailTask.id}`); detailDrawerVisible = false">查看详情页</el-button>
          <el-button v-if="detailTask.status === 'running'" type="warning" @click="handleCancel(detailTask.id)">停止任务</el-button>
          <el-button v-if="detailTask.status !== 'running'" type="success" @click="handleRestart(detailTask.id)">重启任务</el-button>
          <el-button type="danger" @click="handleDelete(detailTask.id)">删除任务</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 创建任务弹窗 -->
    <el-dialog v-model="createDialogVisible" title="创建任务" :width="dialogWidth" :fullscreen="isMobile">
      <el-form :model="createForm" :label-width="formLabelWidth" :label-position="formLabelPosition">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="任务名称"><el-input v-model="createForm.name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="任务类型">
              <el-select v-model="createForm.task_type" style="width:100%">
                <el-option value="google_sheet" label="Google Sheet" />
                <el-option value="google_sheet_C4" label="Google Sheet C4" />
                <el-option value="google_sheet_C5" label="Google Sheet C5" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="任务描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="任务配置">
          <el-input v-model="createForm.config" type="textarea" :rows="10" spellcheck="false" placeholder="JSON 格式" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建并启动</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTasks, getTask, createTask, cancelTask, deleteTask, restartTask } from '@/api/task'
import { getTaskRuntimeDetail } from '@/api/admin'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import { useResponsive } from '@/composables/useResponsive'
import { usePolling } from '@/composables/usePolling'

const { isMobile, componentSize, drawerSize, dialogWidth, formLabelPosition, formLabelWidth } = useResponsive()
const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const filters = ref({ status: '', task_type: '', keyword: '' })
const detailDrawerVisible = ref(false)
const detailTask = ref(null)
const detailLoading = ref(false)
const createDialogVisible = ref(false)
const creating = ref(false)
const createForm = reactive({ name: '', task_type: 'google_sheet', description: '', config: '' })

const filterConfig = [
  {
    key: 'status',
    type: 'select',
    placeholder: '状态',
    span: { xs: 24, sm: 6, md: 4 },
    options: [
      { value: 'pending', label: '待执行' },
      { value: 'running', label: '运行中' },
      { value: 'completed', label: '已完成' },
      { value: 'cancelled', label: '已取消' },
      { value: 'error', label: '错误' },
    ],
  },
  {
    key: 'task_type',
    type: 'select',
    placeholder: '类型',
    span: { xs: 24, sm: 6, md: 4 },
    options: [
      { value: 'google_sheet', label: 'Google Sheet' },
      { value: 'google_sheet_C4', label: 'Google Sheet C4' },
      { value: 'google_sheet_C5', label: 'Google Sheet C5' },
    ],
  },
  {
    key: 'keyword',
    type: 'input',
    placeholder: '任务名称 / ID',
    span: { xs: 24, sm: 8, md: 6 },
  },
]

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value }
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.task_type) params.task_type = filters.value.task_type
    if (filters.value.keyword) params.keyword = filters.value.keyword
    const res = await getTasks(params)
    tasks.value = res.tasks || []
    total.value = res.pagination?.total || 0
  } finally { loading.value = false }
}

function doFilter() { page.value = 1; loadTasks() }
function clearFilters() { filters.value = { status: '', task_type: '', keyword: '' }; doFilter() }

usePolling(loadTasks, { interval: 30000, immediate: true })

async function showDetail(id) {
  detailDrawerVisible.value = true
  detailLoading.value = true
  detailTask.value = null
  try {
    const res = await getTaskRuntimeDetail(id)
    detailTask.value = res.task || null
  } catch {
    const res = await getTask(id)
    detailTask.value = res.task || res
  } finally { detailLoading.value = false }
}

async function handleCancel(id) {
  await ElMessageBox.confirm('确定要停止这个任务吗？', '确认停止', { type: 'warning' })
  await cancelTask(id)
  ElMessage.success('已发送停止请求')
  loadTasks()
}

async function handleRestart(id) {
  await restartTask(id)
  ElMessage.success('任务重启成功')
  loadTasks()
}

async function handleDelete(id) {
  await ElMessageBox.confirm('确定要删除这个任务吗？删除后不可恢复。', '确认删除', { type: 'warning' })
  await deleteTask(id)
  ElMessage.success('任务已删除')
  detailDrawerVisible.value = false
  loadTasks()
}

function openCreate() {
  Object.assign(createForm, { name: '', task_type: 'google_sheet', description: '', config: '' })
  createDialogVisible.value = true
}

async function handleCreate() {
  if (!createForm.name || !createForm.config) { ElMessage.warning('请填写必要字段'); return }
  try { JSON.parse(createForm.config) } catch { ElMessage.error('配置格式错误'); return }
  creating.value = true
  try {
    await createTask({ name: createForm.name, task_type: createForm.task_type, description: createForm.description, config: JSON.parse(createForm.config) })
    ElMessage.success('任务创建成功')
    createDialogVisible.value = false
    loadTasks()
  } catch { ElMessage.error('任务创建失败') }
  finally { creating.value = false }
}
</script>

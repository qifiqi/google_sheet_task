<template>
  <div class="">
    <div class="page-toolbar">
      <h2 style="margin:0">任务管理</h2>
      <div class="page-toolbar__actions">
        <el-button type="primary" :size="componentSize" @click="openCreate">创建任务</el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" style="margin-bottom:16px">
      <el-row :gutter="12" align="bottom">
        <el-col :xs="24" :sm="6" :md="4">
          <el-select v-model="filters.status" placeholder="状态" clearable style="width:100%" @change="doFilter">
            <el-option value="pending" label="待执行" />
            <el-option value="running" label="运行中" />
            <el-option value="completed" label="已完成" />
            <el-option value="cancelled" label="已取消" />
            <el-option value="error" label="错误" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="6" :md="4">
          <el-select v-model="filters.task_type" placeholder="类型" clearable style="width:100%" @change="doFilter">
            <el-option value="google_sheet" label="Google Sheet" />
            <el-option value="google_sheet_C4" label="Google Sheet C4" />
            <el-option value="google_sheet_C5" label="Google Sheet C5" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="8" :md="6">
          <el-input v-model="filters.keyword" placeholder="任务名称 / ID" clearable @keyup.enter="doFilter" @clear="doFilter" />
        </el-col>
        <el-col :xs="12" :sm="4" :md="2">
          <el-button @click="clearFilters">清空</el-button>
        </el-col>
        <el-col :xs="12" :sm="4" :md="2">
          <el-button @click="loadTasks">刷新</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never">
      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column label="任务" min-width="160">
          <template #default="{ row }">
            <div style="font-weight:600">{{ row.name }}</div>
            <div style="font-size:11px;color:#909399">{{ row.id?.slice(0,8) }}...</div>
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
            <el-progress v-if="row.total_steps > 0" :percentage="Math.min(100, Math.round((row.current_step||0)/row.total_steps*100))"
              :format="() => `${row.current_step||0}/${row.total_steps}`" />
            <span v-else style="color:#909399">-</span>
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
      </el-table>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;flex-wrap:wrap;gap:8px">
        <span style="color:#909399;font-size:13px">{{ paginationInfo }}</span>
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="sizes, prev, pager, next"
          @current-change="loadTasks"
          @size-change="() => { page = 1; loadTasks() }"
        />
      </div>
    </el-card>

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
          <pre style="background:#f5f7fa;padding:12px;border-radius:4px;overflow:auto;max-height:300px;font-size:12px">{{ JSON.stringify(detailTask.config || {}, null, 2) }}</pre>
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
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTasks, getTask, createTask, cancelTask, deleteTask, restartTask } from '@/api/task'
import { getTaskRuntimeDetail } from '@/api/admin'
import StatusTag from '@/components/StatusTag.vue'
import { useResponsive } from '@/composables/useResponsive'

const { isMobile, componentSize, drawerSize, dialogWidth, formLabelPosition, formLabelWidth } = useResponsive()
const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const filters = reactive({ status: '', task_type: '', keyword: '' })
const detailDrawerVisible = ref(false)
const detailTask = ref(null)
const detailLoading = ref(false)
const createDialogVisible = ref(false)
const creating = ref(false)
const createForm = reactive({ name: '', task_type: 'google_sheet', description: '', config: '' })
let refreshTimer = null

const paginationInfo = computed(() => {
  if (!total.value) return '暂无数据'
  const start = (page.value - 1) * pageSize.value + 1
  const end = Math.min(page.value * pageSize.value, total.value)
  return `显示第 ${start}-${end} 条，共 ${total.value} 条`
})

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value }
    if (filters.status) params.status = filters.status
    if (filters.task_type) params.task_type = filters.task_type
    if (filters.keyword) params.keyword = filters.keyword
    const res = await getTasks(params)
    tasks.value = res.tasks || []
    total.value = res.pagination?.total || 0
  } finally { loading.value = false }
}

function doFilter() { page.value = 1; loadTasks() }
function clearFilters() { filters.status = ''; filters.task_type = ''; filters.keyword = ''; doFilter() }

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

onMounted(() => {
  loadTasks()
  refreshTimer = setInterval(loadTasks, 30000)
})
onUnmounted(() => clearInterval(refreshTimer))
</script>

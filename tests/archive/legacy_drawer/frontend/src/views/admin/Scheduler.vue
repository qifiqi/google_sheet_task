<template>
  <div class="app-page scheduler-page">
    <PageToolbar eyebrow="管理后台" title="定时任务管理">
      <template #actions>
        <el-button type="primary" @click="openCreate">添加定时任务</el-button>
      </template>
    </PageToolbar>

    <StatCardGrid :cards="statCards" :data="stats" variant="gradient" />

    <el-card shadow="never">
      <template #header>定时任务列表</template>
      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="任务名称" min-width="140" />
        <el-table-column prop="description" label="描述" min-width="120" show-overflow-tooltip />
        <el-table-column label="Cron 表达式" width="160">
          <template #default="{ row }">
            <code class="mono-inline">{{ row.cron_expression }}</code>
          </template>
        </el-table-column>
        <el-table-column label="任务类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ taskTypeText(row.task_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="run_count" label="执行次数" width="80" />
        <el-table-column prop="last_run_time" label="上次执行" width="160" show-overflow-tooltip />
        <el-table-column prop="next_run_time" label="下次执行" width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link :type="row.is_active ? 'warning' : 'success'" @click="handleToggle(row)">{{ row.is_active ? '禁用' : '启用' }}</el-button>
            <el-button link type="info" @click="handleRunNow(row.id)">立即执行</el-button>
            <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑定时任务' : '添加定时任务'" width="600px" :fullscreen="isMobile">
      <el-form :model="form" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="任务名称">
              <el-input v-model="form.name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="任务类型">
              <el-select v-model="form.task_type" class="full-width">
                <el-option value="cleanup" label="数据清理" />
                <el-option value="backup" label="数据备份" />
                <el-option value="maintenance" label="系统维护" />
                <el-option value="custom" label="自定义" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="任务描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="Cron 表达式">
              <el-input v-model="form.cron_expression" placeholder="如: 0 0 * * *" />
              <div class="helper-text">格式：分 时 日 月 周</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="执行函数">
              <el-select v-model="form.task_function" class="full-width">
                <el-option value="cleanup_old_logs" label="清理旧日志" />
                <el-option value="cleanup_old_results" label="清理旧结果" />
                <el-option value="cleanup_old_data" label="清理旧数据" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="任务参数">
          <el-input v-model="form.task_params" type="textarea" :rows="3" placeholder='{"days": 10}' />
          <div class="helper-text">JSON 格式，例如 {"days": 10}</div>
        </el-form-item>
        <el-form-item label="启用任务">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">{{ editingId ? '更新任务' : '添加任务' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getSchedulerStats, getScheduledTasks, createScheduledTask, updateScheduledTask, deleteScheduledTask, toggleScheduledTask, runScheduledTask } from '@/api/scheduler'
import { useResponsive } from '@/composables/useResponsive'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import { usePolling } from '@/composables/usePolling'

const { isMobile } = useResponsive()
const tasks = ref([])
const stats = ref({})
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)

const statCards = [
  { key: 'total_tasks', label: '总任务数', background: '#409eff' },
  { key: 'active_tasks', label: '活跃任务', background: '#67c23a' },
  { key: 'inactive_tasks', label: '暂停任务', background: '#e6a23c' },
  { key: 'scheduler_running', label: '调度器状态', background: '#17a2b8' },
]

const form = reactive({ name: '', description: '', cron_expression: '', task_type: 'cleanup', task_function: 'cleanup_old_logs', task_params: '', is_active: true })

const taskTypeMap = { cleanup: '数据清理', backup: '数据备份', maintenance: '系统维护', custom: '自定义' }
const taskTypeText = (t) => taskTypeMap[t] || t

async function loadAll() {
  loading.value = true
  try {
    const [tRes, sRes] = await Promise.all([getScheduledTasks(), getSchedulerStats()])
    tasks.value = tRes.tasks || []
    const s = sRes.stats || {}
    stats.value = { ...s, scheduler_running: s.scheduler_running ? '运行中' : '已停止' }
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', description: '', cron_expression: '', task_type: 'cleanup', task_function: 'cleanup_old_logs', task_params: '', is_active: true })
  dialogVisible.value = true
}

function openEdit(task) {
  editingId.value = task.id
  form.name = task.name
  form.description = task.description || ''
  form.cron_expression = task.cron_expression
  form.task_type = task.task_type
  form.task_function = task.task_function
  form.task_params = JSON.stringify(task.task_params || {}, null, 2)
  form.is_active = task.is_active
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.name || !form.cron_expression || !form.task_type || !form.task_function) {
    ElMessage.warning('请填写所有必填字段')
    return
  }
  if (form.task_params) {
    try {
      JSON.parse(form.task_params)
    } catch {
      ElMessage.error('任务参数必须是有效的 JSON 格式')
      return
    }
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateScheduledTask(editingId.value, form)
    } else {
      await createScheduledTask(form)
    }
    ElMessage.success(editingId.value ? '任务更新成功' : '任务添加成功')
    dialogVisible.value = false
    loadAll()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleToggle(task) {
  await toggleScheduledTask(task.id)
  ElMessage.success(`任务已${task.is_active ? '禁用' : '启用'}`)
  loadAll()
}

async function handleRunNow(id) {
  await ElMessageBox.confirm('确定要立即执行这个任务吗？', '确认执行', { type: 'info' })
  await runScheduledTask(id)
  ElMessage.success('任务已开始执行')
  loadAll()
}

async function handleDelete(id) {
  await ElMessageBox.confirm('确定要删除这个定时任务吗？此操作不可恢复。', '确认删除', { type: 'warning' })
  await deleteScheduledTask(id)
  ElMessage.success('任务删除成功')
  loadAll()
}

usePolling(loadAll, { interval: 30000 })
</script>

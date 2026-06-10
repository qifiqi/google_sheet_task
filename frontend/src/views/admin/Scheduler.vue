<template>
  <div class="admin-scheduler">
    <PageToolbar eyebrow="管理中心" title="定时任务" description="管理系统定时任务调度">
      <template #actions>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon> 创建定时任务
        </el-button>
      </template>
    </PageToolbar>

    <StatCardGrid
      :cards="STAT_CARDS"
      :data="statsData"
      :columns="{ xs: 12, sm: 6, md: 6 }"
      variant="gradient"
      class="mb-4"
    />

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>任务列表</span>
          <el-button text type="primary" @click="loadData">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
      <el-table :data="tasks" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="name" label="任务名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="task_type" label="类型" width="130" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.task_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="cron_expression" label="Cron 表达式" width="150" align="center">
          <template #default="{ row }">
            <code class="cron-code">{{ row.cron_expression }}</code>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              @change="handleToggle(row)"
              size="small"
            />
          </template>
        </el-table-column>
        <el-table-column prop="last_run_at" label="上次执行" width="175" align="center">
          <template #default="{ row }">
            <span class="cell-time">{{ formatTime(row.last_run_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="next_run_at" label="下次执行" width="175" align="center">
          <template #default="{ row }">
            <span class="cell-time">{{ formatTime(row.next_run_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="success" size="small" text @click="handleRunNow(row)">执行</el-button>
            <el-button type="primary" size="small" text @click="openEditDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除此定时任务？" @confirm="handleDelete(row)">
              <template #reference>
                <el-button type="danger" size="small" text @click.stop>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑定时任务' : '创建定时任务'"
      width="600px"
      destroy-on-close
    >
      <el-form :model="form" label-width="120px" ref="formRef">
        <el-form-item label="任务名称" required>
          <el-input v-model="form.name" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="任务类型" required>
          <el-select v-model="form.task_type" placeholder="选择类型" style="width: 100%">
            <el-option label="C3 参数校验" value="c3" />
            <el-option label="C4 参数校验" value="c4" />
            <el-option label="C5 参数校验" value="c5" />
            <el-option label="回测训练" value="backtest_training" />
            <el-option label="多品种回测" value="backtest_multi" />
            <el-option label="模型汇总重建" value="model_summary_rebuild" />
          </el-select>
        </el-form-item>
        <el-form-item label="Cron 表达式" required>
          <el-input v-model="form.cron_expression" placeholder="例: 0 2 * * * (每天凌晨2点)">
            <template #append>
              <el-tooltip content="标准 5 位 Cron 表达式：分 时 日 月 周" placement="top">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="配置 (JSON)">
          <el-input
            v-model="form.config_json"
            type="textarea"
            :rows="6"
            placeholder="任务配置参数（可选）"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
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
import { ref, onMounted } from 'vue'
import { Plus, Refresh, QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getScheduledTasks,
  createScheduledTask,
  updateScheduledTask,
  deleteScheduledTask,
  toggleScheduledTask,
  runScheduledTask,
  getSchedulerStats,
} from '@/api/scheduler'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'

const loading = ref(false)
const tasks = ref([])
const statsData = ref({ total: 0, active: 0, today_runs: 0, failed: 0 })

const STAT_CARDS = [
  { key: 'total', label: '总任务数', background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)' },
  { key: 'active', label: '已启用', background: 'linear-gradient(135deg, #10b981, #059669)' },
  { key: 'today_runs', label: '今日执行', background: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  { key: 'failed', label: '失败次数', background: 'linear-gradient(135deg, #ef4444, #dc2626)' },
]

// Dialog
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const saving = ref(false)
const form = ref({
  id: null,
  name: '',
  task_type: '',
  cron_expression: '',
  config_json: '',
  is_active: true,
})

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

async function loadData() {
  loading.value = true
  try {
    const [statsRes, tasksRes] = await Promise.allSettled([
      getSchedulerStats(),
      getScheduledTasks(),
    ])

    if (statsRes.status === 'fulfilled') {
      const data = statsRes.value?.data || statsRes.value || {}
      statsData.value = {
        total: data.total ?? 0,
        active: data.active ?? 0,
        today_runs: data.today_runs ?? 0,
        failed: data.failed ?? 0,
      }
    }

    if (tasksRes.status === 'fulfilled') {
      const data = tasksRes.value?.data || tasksRes.value || {}
      tasks.value = data.tasks || data.items || data || []
    }
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  isEdit.value = false
  form.value = { id: null, name: '', task_type: '', cron_expression: '', config_json: '', is_active: true }
  dialogVisible.value = true
}

function openEditDialog(row) {
  isEdit.value = true
  form.value = {
    id: row.id,
    name: row.name,
    task_type: row.task_type,
    cron_expression: row.cron_expression,
    config_json: typeof row.config === 'string' ? row.config : JSON.stringify(row.config || {}, null, 2),
    is_active: row.is_active ?? true,
  }
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.value.name || !form.value.task_type || !form.value.cron_expression) {
    ElMessage.warning('请填写必要字段')
    return
  }

  let config = {}
  if (form.value.config_json) {
    try {
      config = JSON.parse(form.value.config_json)
    } catch {
      ElMessage.warning('配置 JSON 格式无效')
      return
    }
  }

  saving.value = true
  try {
    const payload = {
      name: form.value.name,
      task_type: form.value.task_type,
      cron_expression: form.value.cron_expression,
      config,
      is_active: form.value.is_active,
    }
    if (isEdit.value) {
      await updateScheduledTask(form.value.id, payload)
      ElMessage.success('已更新')
    } else {
      await createScheduledTask(payload)
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    loadData()
  } catch {
    ElMessage.error(isEdit.value ? '更新失败' : '创建失败')
  } finally {
    saving.value = false
  }
}

async function handleToggle(row) {
  try {
    await toggleScheduledTask(row.id)
    ElMessage.success(row.is_active ? '已禁用' : '已启用')
    loadData()
  } catch {
    ElMessage.error('操作失败')
  }
}

async function handleRunNow(row) {
  try {
    await ElMessageBox.confirm('确定立即执行此任务？', '确认')
    await runScheduledTask(row.id)
    ElMessage.success('已触发执行')
    loadData()
  } catch { /* cancelled */ }
}

async function handleDelete(row) {
  try {
    await deleteScheduledTask(row.id)
    ElMessage.success('已删除')
    loadData()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(loadData)
</script>

<style lang="scss" scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mb-4 {
  margin-bottom: 16px;
}

.cron-code {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  background: var(--el-fill-color-light);
  padding: 2px 8px;
  border-radius: 4px;
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>

<script setup lang="ts">
import { onMounted, shallowRef } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SchedulerMetricGrid from '../../components/scheduler/SchedulerMetricGrid.vue'
import SchedulerTaskDialog from '../../components/scheduler/SchedulerTaskDialog.vue'
import SchedulerTaskTable from '../../components/scheduler/SchedulerTaskTable.vue'
import { useAuthStore } from '../../stores/auth'
import { useScheduledTasks } from '../../composables/useScheduledTasks'
import type { SchedulerTaskPayload, ScheduledTask } from '../../types/api'
import { scheduledTaskTypeOptions } from '../../utils/scheduler'
import '../../styles/scheduler/scheduler-page.css'

const auth = useAuthStore()
const scheduler = useScheduledTasks()
const dialogVisible = shallowRef(false)
const editingTask = shallowRef<ScheduledTask | null>(null)
const saving = shallowRef(false)

function canManage() { return auth.hasPermission('scheduler:manage') }
function openCreate() { editingTask.value = null; dialogVisible.value = true }
function openEdit(task: ScheduledTask) { editingTask.value = task; dialogVisible.value = true }

async function save(payload: SchedulerTaskPayload) {
  saving.value = true
  try {
    if (editingTask.value) {
      await scheduler.update(editingTask.value.id, payload)
      ElMessage.success('定时任务已更新')
    } else {
      await scheduler.create(payload)
      ElMessage.success('定时任务已创建')
    }
    dialogVisible.value = false
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存定时任务失败')
  } finally {
    saving.value = false
  }
}

async function toggle(task: ScheduledTask) {
  try {
    await scheduler.toggle(task)
    ElMessage.success(`定时任务已${task.is_active ? '停用' : '启用'}`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '更新任务状态失败')
  }
}

async function run(task: ScheduledTask) {
  try {
    await ElMessageBox.confirm(`确定立即执行“${task.name}”吗？`, '立即执行', { type: 'warning', confirmButtonText: '执行' })
    await scheduler.run(task)
    ElMessage.success('任务已提交后台执行')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '提交执行失败')
  }
}

async function remove(task: ScheduledTask) {
  try {
    await ElMessageBox.confirm(`删除“${task.name}”后无法恢复，是否继续？`, '删除定时任务', { type: 'error', confirmButtonText: '删除' })
    await scheduler.remove(task)
    ElMessage.success('定时任务已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '删除定时任务失败')
  }
}

function search() { scheduler.load(1) }
function reset() { scheduler.resetFilters(); scheduler.load(1) }

onMounted(scheduler.load)
</script>

<template>
  <section class="scheduler-page">
    <header class="scheduler-page__header"><div><p>调度模块</p><h1>定时任务</h1></div><el-button v-if="canManage()" type="primary" :icon="Plus" @click="openCreate">新建定时任务</el-button></header>
    <SchedulerMetricGrid :stats="scheduler.stats.value" />
    <section class="scheduler-page__panel">
      <div class="scheduler-page__toolbar">
        <el-input v-model="scheduler.filters.keyword" clearable placeholder="搜索任务名称或说明" @keyup.enter="search" />
        <el-select v-model="scheduler.filters.taskType" clearable placeholder="全部类型"><el-option v-for="item in scheduledTaskTypeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
        <el-select v-model="scheduler.filters.active" clearable placeholder="全部状态"><el-option label="已启用" value="true" /><el-option label="已停用" value="false" /></el-select>
        <div class="scheduler-page__toolbar-actions"><el-button type="primary" @click="search">查询</el-button><el-button @click="reset">重置</el-button><el-button text :icon="Refresh" aria-label="刷新定时任务列表" @click="() => scheduler.load()" /></div>
      </div>
      <el-alert v-if="scheduler.errorMessage.value" :title="scheduler.errorMessage.value" type="error" show-icon :closable="false" />
      <SchedulerTaskTable :tasks="scheduler.tasks.value" :loading="scheduler.loading.value" :can-manage="canManage()" @edit="openEdit" @toggle="toggle" @run="run" @remove="remove" />
      <footer class="scheduler-page__pagination"><span>共 {{ scheduler.pagination.total }} 条</span><el-pagination v-model:current-page="scheduler.pagination.page" v-model:page-size="scheduler.pagination.per_page" background layout="total, sizes, prev, pager, next, jumper" :page-sizes="[10, 20, 50]" :total="scheduler.pagination.total" @current-change="scheduler.load" @size-change="() => scheduler.load(1)" /></footer>
    </section>
    <SchedulerTaskDialog v-model="dialogVisible" :task="editingTask" :submitting="saving" @save="save" />
  </section>
</template>

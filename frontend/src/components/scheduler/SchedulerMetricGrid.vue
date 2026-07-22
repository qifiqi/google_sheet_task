<script setup lang="ts">
import { CircleCheckFilled, Clock, Connection, VideoPause } from '@element-plus/icons-vue'
import type { SchedulerStats } from '../../types/api'

defineProps<{ stats: SchedulerStats }>()
</script>

<template>
  <div class="scheduler-metric-grid" aria-label="调度概览">
    <div class="scheduler-metric-grid__item"><span>定时任务总数</span><strong>{{ stats.total_tasks }}</strong><el-icon><Clock /></el-icon></div>
    <div class="scheduler-metric-grid__item"><span>已启用</span><strong class="is-success">{{ stats.active_tasks }}</strong><el-icon class="is-success"><CircleCheckFilled /></el-icon></div>
    <div class="scheduler-metric-grid__item"><span>已停用</span><strong class="is-info">{{ stats.inactive_tasks }}</strong><el-icon><VideoPause /></el-icon></div>
    <div class="scheduler-metric-grid__item"><span>调度器</span><strong :class="stats.scheduler_running ? 'is-success' : 'is-danger'">{{ stats.scheduler_running ? '运行中' : '已停止' }}</strong><el-icon :class="stats.scheduler_running ? 'is-success' : 'is-danger'"><Connection /></el-icon></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardExecutionHealth, DashboardSummary } from '../../types/api'

const props = defineProps<{
  health: DashboardExecutionHealth
  summary: DashboardSummary
  completionRate: number
}>()

const xplCompletionRate = computed(() => {
  const total = props.health.xpl_jobs.total
  return total ? Math.round((props.health.xpl_jobs.completed / total) * 100) : 0
})
</script>

<template>
  <el-card shadow="never" class="health-card">
    <template #header>
      <div class="health-card__header">
        <div>
          <strong>执行健康</strong>
          <span>任务结果与 XPL 队列</span>
        </div>
        <el-tag effect="plain" type="success" size="small">实时</el-tag>
      </div>
    </template>

    <section class="health-section">
      <div class="health-section__title">
        <span>任务完成率</span>
        <strong>{{ completionRate }}%</strong>
      </div>
      <el-progress :percentage="completionRate" :show-text="false" :stroke-width="8" />
      <div class="health-section__meta">
        <span>完成 {{ summary.completed_tasks }}</span>
        <span>总数 {{ summary.total_tasks }}</span>
      </div>
    </section>

    <section class="health-section">
      <div class="health-section__title">
        <span>结果成功率</span>
        <strong>{{ health.results.success_rate.toFixed(1) }}%</strong>
      </div>
      <el-progress
        :percentage="Math.round(health.results.success_rate)"
        :show-text="false"
        :stroke-width="8"
        color="var(--admin-success)"
      />
      <div class="health-section__meta">
        <span>成功 {{ health.results.success }}</span>
        <span>失败 {{ health.results.failed }}</span>
      </div>
    </section>

    <section class="health-section health-section--xpl">
      <div class="health-section__title">
        <span>XPL 完成率</span>
        <strong>{{ xplCompletionRate }}%</strong>
      </div>
      <div class="xpl-stats">
        <span><strong>{{ health.xpl_jobs.backlog }}</strong>积压</span>
        <span><strong>{{ health.xpl_jobs.running }}</strong>执行中</span>
        <span><strong>{{ health.xpl_jobs.error }}</strong>异常</span>
      </div>
      <small v-if="health.xpl_jobs.avg_compute_seconds !== null && health.xpl_jobs.avg_compute_seconds !== undefined">
        平均计算 {{ health.xpl_jobs.avg_compute_seconds.toFixed(2) }} 秒
      </small>
    </section>
  </el-card>
</template>

<style scoped>
.health-card__header,
.health-section__title,
.health-section__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.health-card__header > div {
  display: grid;
  gap: 4px;
}

.health-card__header strong {
  color: var(--admin-text);
  font-size: 16px;
}

.health-card__header span,
.health-section__meta,
.health-section small {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.health-section {
  display: grid;
  gap: 10px;
  padding: 4px 18px;
}

.health-section + .health-section {
  border-left: 1px solid var(--admin-border-light);
}

.health-section__title span {
  color: var(--admin-text-regular);
  font-weight: 600;
}

.health-section__title strong {
  color: var(--admin-text);
  font-size: 18px;
}

.health-section--xpl {
  padding-bottom: 4px;
}

.xpl-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.xpl-stats span {
  display: grid;
  gap: 2px;
  padding: 8px;
  border-radius: 6px;
  background: var(--admin-bg);
  color: var(--admin-text-muted);
  font-size: 11px;
  text-align: center;
}

.xpl-stats strong {
  color: var(--admin-text);
  font-size: 16px;
}

.health-card :deep(.el-card__body) {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: stretch;
  padding: 18px 0;
}

@media (max-width: 760px) {
  .health-card :deep(.el-card__body) {
    grid-template-columns: 1fr;
    gap: 18px;
  }

  .health-section + .health-section {
    border-top: 1px solid var(--admin-border-light);
    border-left: 0;
    padding-top: 18px;
  }
}
</style>

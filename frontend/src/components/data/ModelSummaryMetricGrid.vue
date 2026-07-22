<script setup lang="ts">
import { computed } from 'vue'
import type { ModelSummaryStatistics } from '../../types/api'
import '../../styles/data/model-summary-cards.css'

const props = defineProps<{ summary: ModelSummaryStatistics; summaryType: 'task' | 'stock' }>()
const denominator = computed(() => props.summaryType === 'stock' ? props.summary.stock_count : props.summary.task_count)
const marketShare = computed(() => props.summary.stock_count ? (props.summary.cn_stock_count / props.summary.stock_count) * 100 : 0)
const metrics = computed(() => [
  { label: '> 0%', value: props.summary.return_beats_gt_0, tone: 'positive' },
  { label: '> 20%', value: props.summary.return_beats_gt_20, tone: 'medium' },
  { label: '> 50%', value: props.summary.return_beats_gt_50, tone: 'strong' },
  { label: '> 100%', value: props.summary.return_beats_gt_100, tone: 'extreme' },
])
function rate(value: number) { return denominator.value ? Math.min(100, (value / denominator.value) * 100) : 0 }
</script>

<template>
  <div class="summary-card-grid summary-card-grid--option-one">
    <section class="summary-market-card">
      <div class="summary-card-title">市场结构</div>
      <div class="summary-main-row"><div class="summary-main-number">{{ summary.stock_count }}</div><div class="summary-main-label">股票总数</div></div>
      <el-progress class="market-share-bar" :percentage="marketShare" :stroke-width="6" :show-text="false" />
      <div class="market-inline-row">
        <div class="market-row"><span><i class="market-dot market-dot--cn" />A股</span><strong>{{ summary.cn_stock_count }}</strong></div>
        <div class="market-row"><span><i class="market-dot market-dot--us" />美股</span><strong>{{ summary.us_stock_count }}</strong></div>
      </div>
      <div class="market-task-row"><span>任务总数</span><strong>{{ summary.task_count }}</strong></div>
    </section>
    <section v-for="item in metrics" :key="item.label" class="return-threshold-card" :class="`return-threshold-card--${item.tone}`">
      <div class="return-card-title">ReturnBeats</div>
      <div class="return-card-threshold">{{ item.label }}</div>
      <div class="return-card-count">{{ item.value }}</div>
      <el-progress class="return-progress" :percentage="rate(item.value)" :stroke-width="5" :show-text="false" />
      <div class="return-card-caption">占筛选{{ summaryType === 'stock' ? '标的' : '任务' }}</div>
      <div class="return-card-rate">{{ rate(item.value).toFixed(1) }}%</div>
    </section>
  </div>
</template>

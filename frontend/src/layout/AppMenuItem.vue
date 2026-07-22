<script setup lang="ts">
import { computed } from 'vue'
import {
  Aim,
  Calendar,
  ChatDotRound,
  CirclePlus,
  Collection,
  Connection,
  CopyDocument,
  Cpu,
  DataAnalysis,
  DataBoard,
  Document,
  DocumentAdd,
  DocumentChecked,
  Files,
  Guide,
  Grid,
  Histogram,
  HomeFilled,
  List,
  Lock,
  Memo,
  Notebook,
  PieChart,
  Setting,
  SetUp,
  Tickets,
  Timer,
  TrendCharts,
  User,
} from '@element-plus/icons-vue'
import type { Component } from 'vue'
import type { NavItem } from '../types/api'

const props = defineProps<{
  item: NavItem
}>()

const iconMap: Record<string, Component> = {
  dashboard: HomeFilled,
  task: Tickets,
  tasks: List,
  templates: Files,
  results: DocumentChecked,
  xpl_analysis_jobs: Cpu,
  data: DataAnalysis,
  model_summary: TrendCharts,
  scheduler_group: Timer,
  scheduler: Calendar,
  system: Setting,
  config: SetUp,
  sheets: Connection,
  navigation: Guide,
  logs: Memo,
  users: User,
  roles: Lock,
  business: Grid,
  c3: Document,
  c4: CopyDocument,
  c5: Collection,
  c7: Notebook,
  backtest: PieChart,
  backtest_create: CirclePlus,
  backtest_multi_product: DataBoard,
  backtest_multi_product_create: DocumentAdd,
  xpl: Aim,
  xpl_v1: Histogram,
}

const itemIcon = computed(() => iconMap[props.item.key] || iconMap[props.item.parent_key || ''] || ChatDotRound)
const hasChildren = computed(() => Boolean(props.item.children?.length))
const menuIndex = computed(() => props.item.path || props.item.key)
</script>

<template>
  <el-sub-menu v-if="hasChildren" :index="menuIndex">
    <template #title>
      <el-icon><component :is="itemIcon" /></el-icon>
      <span>{{ item.label }}</span>
    </template>
    <AppMenuItem v-for="child in item.children" :key="child.key" :item="child" />
  </el-sub-menu>

  <el-menu-item v-else :index="menuIndex">
    <el-icon><component :is="itemIcon" /></el-icon>
    <template #title>{{ item.label }}</template>
  </el-menu-item>
</template>

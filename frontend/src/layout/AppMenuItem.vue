<script setup lang="ts">
import { computed } from 'vue'
import {
  ChatDotRound,
  Collection,
  DataAnalysis,
  Document,
  Files,
  Grid,
  HomeFilled,
  Monitor,
  Operation,
  Platform,
  Setting,
  Tools,
  TrendCharts,
} from '@element-plus/icons-vue'
import type { Component } from 'vue'
import type { NavItem } from '../types/api'

const props = defineProps<{
  item: NavItem
}>()

const iconMap: Record<string, Component> = {
  dashboard: HomeFilled,
  task: Tools,
  tasks: Tools,
  data: DataAnalysis,
  scheduler_group: Operation,
  system: Setting,
  business: Grid,
  config: Setting,
  logs: Document,
  templates: Files,
  results: Collection,
  users: Platform,
  roles: Platform,
  navigation: Operation,
  model_summary: TrendCharts,
  xpl_analysis_jobs: Monitor,
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

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import GlobalPreviewView from '../analysis/GlobalPreviewView.vue'

const route = useRoute()
const taskId = computed(() => String(route.params.taskId || ''))
</script>

<template>
  <GlobalPreviewView source="backtest-multi-product" :task-id="taskId" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AnalysisResultView from '../analysis/AnalysisResultView.vue'

const route = useRoute()
const resultId = computed(() => String(route.params.resultId || ''))
</script>

<template>
  <AnalysisResultView source="backtest-training" :result-id="resultId" />
</template>

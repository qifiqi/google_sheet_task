<template>
  <div class="chart-panel" :style="{ height }">
    <div v-if="loading" class="chart-panel__loading" v-loading="true" />
    <slot v-else />
  </div>
</template>

<script setup>
defineProps({
  height: { type: String, default: '260px' },
  loading: { type: Boolean, default: false },
})
</script>

<style lang="scss" scoped>
.chart-panel {
  position: relative;
  width: 100%;

  &__loading {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  canvas {
    width: 100% !important;
  }
}
</style>

<template>
  <div class="log-viewer" :style="{ height }">
    <div v-if="$slots.toolbar" class="log-viewer__toolbar">
      <slot name="toolbar" />
    </div>
    <div ref="containerRef" class="log-viewer__container" @scroll="handleScroll">
      <div v-if="loading" class="log-viewer__loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        加载中...
      </div>
      <template v-else-if="logs.length">
        <!-- Virtual scrolling for large log sets -->
        <template v-if="logs.length > virtualThreshold">
          <div :style="{ height: `${totalHeight}px`, position: 'relative' }">
            <div :style="{ transform: `translateY(${offsetY}px)` }">
              <div
                v-for="(log, idx) in visibleLogs"
                :key="startIndex + idx"
                class="log-viewer__line"
                :class="[`log-viewer__line--${log.level || 'info'}`]"
              >
                <span v-if="log.timestamp" class="log-viewer__ts">{{ log.timestamp }}</span>
                <span v-if="log.level" class="log-viewer__level">[{{ log.level.toUpperCase() }}]</span>
                <span class="log-viewer__msg">{{ log.message }}</span>
              </div>
            </div>
          </div>
        </template>
        <!-- Normal rendering for small log sets -->
        <template v-else>
          <div
            v-for="(log, idx) in logs"
            :key="idx"
            class="log-viewer__line"
            :class="[`log-viewer__line--${log.level || 'info'}`]"
          >
            <span v-if="log.timestamp" class="log-viewer__ts">{{ log.timestamp }}</span>
            <span v-if="log.level" class="log-viewer__level">[{{ log.level.toUpperCase() }}]</span>
            <span class="log-viewer__msg">{{ log.message }}</span>
          </div>
        </template>
      </template>
      <div v-else class="log-viewer__empty">暂无日志</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { Loading } from '@element-plus/icons-vue'

const props = defineProps({
  logs: { type: Array, default: () => [] },
  height: { type: String, default: '500px' },
  autoScroll: { type: Boolean, default: true },
  loading: { type: Boolean, default: false },
  virtualThreshold: { type: Number, default: 500 },
})

const emit = defineEmits(['scroll-top'])
const containerRef = ref(null)

const LINE_HEIGHT = 22
const BUFFER = 10

const scrollTop = ref(0)
const containerHeight = ref(500)

const totalHeight = computed(() => props.logs.length * LINE_HEIGHT)
const startIndex = computed(() => Math.max(0, Math.floor(scrollTop.value / LINE_HEIGHT) - BUFFER))
const endIndex = computed(() => Math.min(props.logs.length, Math.ceil((scrollTop.value + containerHeight.value) / LINE_HEIGHT) + BUFFER))
const visibleLogs = computed(() => props.logs.slice(startIndex.value, endIndex.value))
const offsetY = computed(() => startIndex.value * LINE_HEIGHT)

watch(
  () => props.logs.length,
  () => {
    if (props.autoScroll && props.logs.length <= props.virtualThreshold) {
      nextTick(() => {
        const el = containerRef.value
        if (el) el.scrollTop = el.scrollHeight
      })
    }
  }
)

function handleScroll() {
  const el = containerRef.value
  if (!el) return
  scrollTop.value = el.scrollTop
  containerHeight.value = el.clientHeight
  if (el.scrollTop === 0) {
    emit('scroll-top')
  }
}
</script>

<style lang="scss" scoped>
.log-viewer {
  display: flex;
  flex-direction: column;
  border-radius: var(--el-border-radius-base);
  overflow: hidden;
  border: 1px solid var(--app-border);

  &__toolbar {
    padding: 8px 12px;
    border-bottom: 1px solid var(--app-border);
    background: var(--app-surface);
  }

  &__container {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
    background: #0b1220;
    font-family: 'Fira Code', 'Consolas', monospace;
    font-size: 12px;
    line-height: 1.7;
  }

  &__line {
    white-space: pre-wrap;
    word-break: break-all;

    &--info { color: #93c5fd; }
    &--warning { color: #fbbf24; }
    &--error { color: #f87171; }
    &--debug { color: #a5b4fc; }
    &--success { color: #6ee7b7; }
  }

  &__ts {
    color: #64748b;
    margin-right: 8px;
  }

  &__level {
    margin-right: 8px;
    font-weight: 600;
  }

  &__msg {
    color: inherit;
  }

  &__loading,
  &__empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #64748b;
    gap: 8px;
  }
}
</style>

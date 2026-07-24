<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { formatDateTime } from '../../utils/format'
import type { SystemLogEntry } from '../../types/system'

const props = defineProps<{
  logs: readonly SystemLogEntry[]
  loading?: boolean
}>()

const scrollbar = ref<{ setScrollTop: (value: number) => void }>()

function normalizedLevel(level: string) {
  return level.toLowerCase() || 'info'
}

watch(
  () => props.logs,
  async () => {
    await nextTick()
    scrollbar.value?.setScrollTop(0)
  },
)
</script>

<template>
  <section class="system-log-viewer" v-loading="loading" aria-label="系统日志内容">
    <header class="system-log-viewer__header">
      <div class="system-log-viewer__title">
        <el-icon><Document /></el-icon>
        <span>日志输出</span>
        <el-tag size="small" effect="dark">{{ logs.length }}</el-tag>
      </div>
    </header>
    <el-scrollbar ref="scrollbar" class="system-log-viewer__scroll" always :min-size="36">
      <div v-if="logs.length" class="system-log-viewer__stream" role="log">
        <div
          v-for="(log, index) in logs"
          :key="`${log.timestamp || 'unknown'}-${index}`"
          class="system-log-viewer__line"
          :class="`is-${normalizedLevel(log.level)}`"
        >
          <span class="system-log-viewer__time">[{{ formatDateTime(log.timestamp) }}]</span>
          <span class="system-log-viewer__level">[{{ normalizedLevel(log.level).toUpperCase() }}]</span>
          <span class="system-log-viewer__source">[{{ log.source || 'unknown' }}]</span>
          <span class="system-log-viewer__message">{{ log.message }}</span>
        </div>
      </div>
      <el-empty v-else description="暂无系统日志" :image-size="72" />
    </el-scrollbar>
  </section>
</template>

<style scoped>
.system-log-viewer { overflow: hidden; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }
.system-log-viewer__header { display: flex; align-items: center; min-height: 44px; padding: 0 14px; border-bottom: 1px solid var(--admin-border); }
.system-log-viewer__title { display: flex; align-items: center; gap: 8px; color: var(--admin-text); font-size: 15px; font-weight: 600; }
.system-log-viewer__title .el-icon { color: var(--admin-primary); font-size: 18px; }
.system-log-viewer__scroll { height: clamp(420px, calc(100vh - 330px), 680px); background: #07111f; }
.system-log-viewer__stream { min-width: 100%; width: max-content; padding: 10px 14px 14px; color: #d6e4f5; font-family: Consolas, "Cascadia Mono", "SFMono-Regular", monospace; font-size: 13px; line-height: 22px; }
.system-log-viewer__line { display: flex; min-width: 100%; width: max-content; gap: 8px; white-space: pre; }
.system-log-viewer__line:hover { background: rgb(148 163 184 / 8%); }
.system-log-viewer__time { color: #7dd3fc; }
.system-log-viewer__level { min-width: 76px; color: #60a5fa; }
.system-log-viewer__source { color: #a5b4fc; }
.system-log-viewer__message { color: #d6e4f5; }
.system-log-viewer__line.is-warning .system-log-viewer__level,
.system-log-viewer__line.is-warning .system-log-viewer__message { color: #fbbf24; }
.system-log-viewer__line.is-error .system-log-viewer__level,
.system-log-viewer__line.is-error .system-log-viewer__message,
.system-log-viewer__line.is-critical .system-log-viewer__level,
.system-log-viewer__line.is-critical .system-log-viewer__message { color: #fb7185; }
.system-log-viewer__line.is-debug .system-log-viewer__level,
.system-log-viewer__line.is-debug .system-log-viewer__message { color: #94a3b8; }
.system-log-viewer :deep(.el-empty__description p) { color: #94a3b8; }
@media (max-width: 640px) { .system-log-viewer__scroll { height: 460px; }.system-log-viewer__stream { font-size: 12px; line-height: 21px; } }
</style>

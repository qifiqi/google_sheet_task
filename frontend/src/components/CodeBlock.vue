<template>
  <div class="code-block" :class="[`code-block--${variant}`]">
    <div v-if="isLarge && collapsed" class="code-block__collapsed" @click="collapsed = false">
      <span>内容较大 ({{ sizeLabel }})，点击展开</span>
    </div>
    <pre v-else :style="{ maxHeight }" class="code-block__pre"><code>{{ formattedContent }}</code></pre>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  content: { type: [String, Object, Array], default: '' },
  maxHeight: { type: String, default: '300px' },
  variant: { type: String, default: 'default' },
})

const collapsed = ref(true)

const formattedContent = computed(() => {
  if (typeof props.content === 'string') return props.content
  try {
    return JSON.stringify(props.content, null, 2)
  } catch {
    return String(props.content)
  }
})

const isLarge = computed(() => formattedContent.value.length > 10240)

const sizeLabel = computed(() => {
  const len = formattedContent.value.length
  if (len > 1048576) return `${(len / 1048576).toFixed(1)} MB`
  return `${(len / 1024).toFixed(1)} KB`
})
</script>

<style lang="scss" scoped>
.code-block {
  border-radius: var(--el-border-radius-base);
  overflow: hidden;

  &--default {
    background: var(--app-surface);
    border: 1px solid var(--app-border);
  }

  &--danger {
    background: rgba(239, 68, 68, 0.06);
    border: 1px solid rgba(239, 68, 68, 0.2);
  }

  &__pre {
    margin: 0;
    padding: 14px 16px;
    overflow: auto;
    font-family: 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    line-height: 1.6;
    color: var(--app-text);
    white-space: pre-wrap;
    word-break: break-all;
  }

  &__collapsed {
    padding: 20px;
    text-align: center;
    color: var(--el-color-primary);
    cursor: pointer;
    font-size: 13px;

    &:hover {
      background: var(--app-surface-elevated);
    }
  }
}
</style>

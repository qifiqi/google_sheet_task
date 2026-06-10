<template>
  <div v-if="hasError" class="error-boundary">
    <div class="error-boundary__card">
      <el-icon :size="48" color="var(--app-danger)"><WarningFilled /></el-icon>
      <h2 class="error-boundary__title">页面渲染出错</h2>
      <p class="error-boundary__desc">{{ errorMessage || '发生了未知错误，请刷新页面重试。' }}</p>
      <div class="error-boundary__actions">
        <el-button type="primary" @click="reload">刷新页面</el-button>
        <el-button @click="goHome">返回首页</el-button>
      </div>
    </div>
  </div>
  <slot v-else />
</template>

<script setup>
import { ref, onErrorCaptured } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

const hasError = ref(false)
const errorMessage = ref('')

onErrorCaptured((err) => {
  hasError.value = true
  errorMessage.value = err?.message || ''
  console.error('[ErrorBoundary]', err)
  return false // Prevent propagation
})

function reload() {
  window.location.reload()
}

function goHome() {
  window.location.href = '/'
}
</script>

<style lang="scss" scoped>
.error-boundary {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;

  &__card {
    text-align: center;
    padding: 48px 40px;
    background: var(--app-surface);
    border: 1px solid var(--app-border);
    border-radius: var(--app-radius-xl);
    box-shadow: var(--app-shadow-lg);
    max-width: 480px;
  }

  &__title {
    font-size: 22px;
    font-weight: 700;
    color: var(--app-text);
    margin: 20px 0 8px;
  }

  &__desc {
    color: var(--app-text-muted);
    margin: 0 0 28px;
    line-height: 1.6;
  }

  &__actions {
    display: flex;
    gap: 12px;
    justify-content: center;
  }
}
</style>

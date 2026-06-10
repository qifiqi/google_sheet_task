<template>
  <div class="forbidden-page">
    <div class="forbidden-card">
      <div class="forbidden-icon">
        <el-icon :size="64" color="var(--app-warning)"><Lock /></el-icon>
      </div>
      <h1 class="forbidden-title">403</h1>
      <p class="forbidden-desc">您没有权限访问此页面</p>
      <p class="forbidden-hint">如需访问，请联系管理员获取相应权限。</p>

      <div class="forbidden-actions">
        <el-button type="primary" size="large" @click="router.push('/task/list')">
          返回任务列表
        </el-button>
        <el-button size="large" @click="router.push('/login')">
          切换账号
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { Lock } from '@element-plus/icons-vue'

const router = useRouter()
</script>

<style lang="scss" scoped>
.forbidden-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--app-bg);
}

.forbidden-card {
  text-align: center;
  padding: 48px 40px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-xl);
  box-shadow: var(--app-shadow-lg);
  max-width: 420px;
}

.forbidden-icon {
  margin-bottom: 24px;
  opacity: 0.8;
}

.forbidden-title {
  font-size: 72px;
  font-weight: 800;
  color: var(--app-text);
  margin: 0;
  line-height: 1;
}

.forbidden-desc {
  font-size: 18px;
  font-weight: 600;
  color: var(--app-text);
  margin: 16px 0 8px;
}

.forbidden-hint {
  color: var(--app-text-muted);
  margin: 0 0 32px;
}

.forbidden-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>

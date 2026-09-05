<template>
  <div class="app-page task-list-page">
    <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
      <n-message-provider>
        <n-dialog-provider>
          <TaskListInner />
        </n-dialog-provider>
      </n-message-provider>
    </n-config-provider>
  </div>
</template>

<script setup>
import { darkTheme } from 'naive-ui'
import { themeOverrides } from '@/styles/naive-theme'
import TaskListInner from './TaskListInner.vue'
</script>

<style scoped>
.task-list-page {
  background: #0a0e1a;
  min-height: 100vh;
}
</style>

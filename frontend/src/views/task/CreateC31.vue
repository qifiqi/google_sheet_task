<template>
  <div>
    <PageToolbar eyebrow="任务创建" title="创建 C31 批量任务" />
    <el-alert type="warning" :closable="false" show-icon class="mb-4">
      C31 批量模式会将配置拆分为多个 C3 子任务并行执行，请确保 Google Sheet 和 Token 配置正确。
    </el-alert>
    <TaskFormCore version="c31" />
  </div>
</template>

<script setup>
import PageToolbar from '@/components/PageToolbar.vue'
import TaskFormCore from './components/TaskFormCore.vue'
</script>

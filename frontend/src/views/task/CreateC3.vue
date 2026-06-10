<template>
  <div>
    <PageToolbar eyebrow="任务创建" title="创建 C3 任务" />
    <TaskFormCore version="c3" />
  </div>
</template>

<script setup>
import PageToolbar from '@/components/PageToolbar.vue'
import TaskFormCore from './components/TaskFormCore.vue'
</script>

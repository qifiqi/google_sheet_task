<template>
  <div>
    <PageToolbar eyebrow="任务创建" title="创建 C4 任务" />
    <TaskFormCore version="c4" />
  </div>
</template>

<script setup>
import PageToolbar from '@/components/PageToolbar.vue'
import TaskFormCore from './components/TaskFormCore.vue'
</script>

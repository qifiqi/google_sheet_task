<template>
  <div class="app-page task-list-page">
    <TaskListInner />
  </div>
</template>

<script setup>
import TaskListInner from './TaskListInner.vue'
</script>

<style scoped>
.task-list-page {
  min-height: 100%;
}
</style>

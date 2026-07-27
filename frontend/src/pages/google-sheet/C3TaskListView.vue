<script setup lang="ts">
import CSeriesTaskList from '../../components/google-sheet/CSeriesTaskList.vue'
</script>

<template>
  <CSeriesTaskList
    title="Google Sheet C3"
    task-type="google_sheet"
    create-url="/web/google-sheet/c3/create"
    batch-create-url="/web/google-sheet/c31/create"
  />
</template>

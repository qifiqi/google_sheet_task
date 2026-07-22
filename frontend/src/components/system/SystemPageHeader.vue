<script setup lang="ts">
defineProps<{ section: string; title: string }>()
</script>

<template>
  <header class="system-page-header">
    <div>
      <p>{{ section }}</p>
      <h1>{{ title }}</h1>
    </div>
    <div class="system-page-header__actions"><slot /></div>
  </header>
</template>

<style scoped>
.system-page-header { display: flex; align-items: end; justify-content: space-between; gap: 16px; }
.system-page-header p { margin: 0 0 2px; color: var(--admin-text-muted); font-size: 13px; }
.system-page-header h1 { margin: 0; color: var(--admin-text); font-size: 20px; font-weight: 600; line-height: 28px; }
.system-page-header__actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
@media (max-width: 640px) { .system-page-header { align-items: flex-start; flex-direction: column; }.system-page-header__actions { justify-content: flex-start; } }
</style>

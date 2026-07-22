<script setup lang="ts">
import { Promotion } from '@element-plus/icons-vue'
import '../../styles/migration/legacy-page-placeholder.css'

const props = defineProps<{
  module: string
  title: string
  legacyPath: string
}>()

function openLegacyPage() {
  window.location.assign(props.legacyPath)
}
</script>

<template>
  <section class="legacy-page-placeholder">
    <header class="legacy-page-placeholder__header">
      <div>
        <p>{{ module }}</p>
        <h1>{{ title }}</h1>
      </div>
    </header>
    <section class="legacy-page-placeholder__panel">
      <el-empty description="页面迁移中" :image-size="72">
        <el-button type="primary" :icon="Promotion" @click="openLegacyPage">打开旧页面</el-button>
      </el-empty>
    </section>
  </section>
</template>

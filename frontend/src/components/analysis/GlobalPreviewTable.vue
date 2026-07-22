<script setup lang="ts">
import type { GlobalPreviewGroup } from '../../types/analysis'
import '../../styles/analysis/global-preview-table.css'

defineProps<{
  group: GlobalPreviewGroup | null
}>()
</script>

<template>
  <section class="global-preview-table">
    <el-empty v-if="!group || group.rows.length === 0" description="当前分组暂无结果" :image-size="64" />
    <template v-else>
      <div class="global-preview-table__meta">
        <el-tag effect="plain">{{ group.group_label }}</el-tag>
        <span>区间：{{ group.period || '-' }}</span>
        <span>参数列：{{ group.column_count || group.columns.length }}</span>
        <span>失败结果：{{ group.failed_results || 0 }}</span>
      </div>
      <el-table :data="[...group.rows]" class="global-preview-table__table" border>
        <el-table-column prop="category" label="指标类型" width="128" />
        <el-table-column prop="metric" label="指标" min-width="180" show-overflow-tooltip />
        <el-table-column prop="index_value" label="指数" min-width="130" show-overflow-tooltip />
        <el-table-column v-for="column in group.columns" :key="column.column_key" :label="column.header || `结果 ${column.result_id || ''}`" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ row.values[column.column_key] || '-' }}</template>
        </el-table-column>
      </el-table>
    </template>
  </section>
</template>

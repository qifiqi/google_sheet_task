<script setup lang="ts">
import { Coin, CopyDocument, Delete, EditPen, Grid, MoreFilled, Promotion, View } from '@element-plus/icons-vue'
import type { TaskTemplate } from '../../types/api'
import { formatDateTime } from '../../utils/format'
import { templateOverview, templateTaskTypeText } from '../../utils/task'

defineProps<{
  items: TaskTemplate[]
  loading: boolean
  canManage: boolean
  canUse: boolean
}>()

const emit = defineEmits<{
  edit: [template: TaskTemplate]
  duplicate: [template: TaskTemplate]
  remove: [template: TaskTemplate]
  preview: [template: TaskTemplate]
  use: [template: TaskTemplate]
}>()

function taskTypeOf(template: TaskTemplate) {
  const value = template.config.task_type
  return templateTaskTypeText(typeof value === 'string' ? value : undefined)
}

function overviewOf(template: TaskTemplate) {
  return templateOverview(template.config)
}
</script>

<template>
  <el-table v-loading="loading" :data="items" class="template-list-table" empty-text="暂无模板">
    <el-table-column label="模板" min-width="270">
      <template #default="{ row }">
        <div class="template-list-table__name">
          <strong>{{ row.name }}</strong>
          <span>{{ row.description || '未填写说明' }}</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="任务类型" width="168">
      <template #default="{ row }">
        <el-tag type="info" effect="plain">{{ taskTypeOf(row) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="资源与标的" min-width="260">
      <template #default="{ row }">
        <div class="template-list-table__resources">
          <el-tag size="small" effect="plain"><el-icon><Grid /></el-icon>{{ overviewOf(row).sheetLabel }}</el-tag>
          <el-tooltip :content="overviewOf(row).stockLabel" :disabled="!overviewOf(row).stockOverflow">
            <el-tag size="small" effect="plain" type="info">{{ overviewOf(row).stockLabel }}<i v-if="overviewOf(row).stockOverflow"> +{{ overviewOf(row).stockOverflow }}</i></el-tag>
          </el-tooltip>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="参数规模" width="168">
      <template #default="{ row }">
        <div class="template-list-table__parameter-count"><el-icon><Coin /></el-icon>{{ overviewOf(row).parameterLabel }}</div>
      </template>
    </el-table-column>
    <el-table-column label="更新时间" width="178">
      <template #default="{ row }">{{ formatDateTime(row.updated_at || row.created_at) }}</template>
    </el-table-column>
    <el-table-column fixed="right" label="操作" width="168">
      <template #default="{ row }">
        <div class="template-list-table__actions">
          <el-button link type="primary" :icon="View" @click="emit('preview', row)">预览</el-button>
          <el-button v-if="canUse" link type="primary" :icon="Promotion" @click="emit('use', row)">使用</el-button>
          <el-dropdown v-if="canManage" trigger="click" @command="(command) => emit(command, row)">
            <el-button link :icon="MoreFilled" aria-label="更多模板操作" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit"><el-icon><EditPen /></el-icon>编辑模板</el-dropdown-item>
                <el-dropdown-item command="duplicate"><el-icon><CopyDocument /></el-icon>复制模板</el-dropdown-item>
                <el-dropdown-item command="remove" divided><el-icon><Delete /></el-icon>删除模板</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.template-list-table { width: 100%; }
.template-list-table__name { display: grid; gap: 3px; min-width: 0; }
.template-list-table__name strong,
.template-list-table__name span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.template-list-table__name strong { color: var(--admin-text); font-weight: 600; }
.template-list-table__name span { color: var(--admin-text-muted); font-size: 12px; }
.template-list-table__resources { display: flex; flex-wrap: wrap; gap: 6px; }
.template-list-table__resources i { color: var(--admin-text-muted); font-style: normal; }
.template-list-table__parameter-count { display: flex; align-items: center; gap: 6px; color: var(--admin-text-regular); font-size: 13px; }
.template-list-table__parameter-count .el-icon { color: var(--admin-text-muted); }
.template-list-table__actions { display: flex; align-items: center; gap: 8px; min-width: max-content; white-space: nowrap; }
.template-list-table__actions :deep(.el-button + .el-button) { margin-left: 0; }
</style>

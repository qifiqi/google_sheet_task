<script setup lang="ts">
import { RefreshRight } from '@element-plus/icons-vue'
import type { XplJob } from '../../types/api'
import { formatDateTime, formatDuration } from '../../utils/format'
import { shortIdentifier, xplStatusText, xplStatusType } from '../../utils/task'

defineProps<{ items: XplJob[]; loading: boolean; canRetry: boolean }>()
const emit = defineEmits<{ retry: [job: XplJob] }>()
</script>

<template>
  <el-table v-loading="loading" :data="items" empty-text="暂无 XPL Job" class="xpl-job-table">
    <el-table-column prop="id" label="Job" width="82" />
    <el-table-column label="状态" width="106"><template #default="{ row }"><el-tag :type="xplStatusType(row.status)">{{ xplStatusText(row.status) }}</el-tag></template></el-table-column>
    <el-table-column label="任务 ID" min-width="156"><template #default="{ row }"><el-tooltip :content="row.task_id || '-'" placement="top"><span>{{ shortIdentifier(row.task_id) }}</span></el-tooltip></template></el-table-column>
    <el-table-column label="结果 ID" width="96"><template #default="{ row }">{{ row.task_result_id || '-' }}</template></el-table-column>
    <el-table-column label="收益序列" width="112"><template #default="{ row }">{{ row.return_series_id || '-' }}</template></el-table-column>
    <el-table-column label="尝试" width="92"><template #default="{ row }">{{ row.attempts || 0 }} / {{ row.max_attempts || '-' }}</template></el-table-column>
    <el-table-column label="读取" width="104"><template #default="{ row }">{{ formatDuration(row.load_elapsed_seconds) }}</template></el-table-column>
    <el-table-column label="计算耗时" width="112"><template #default="{ row }">{{ formatDuration(row.compute_elapsed_seconds) }}</template></el-table-column>
    <el-table-column label="保存" width="104"><template #default="{ row }">{{ formatDuration(row.save_elapsed_seconds) }}</template></el-table-column>
    <el-table-column label="推送状态" width="110"><template #default="{ row }"><el-tag type="info" effect="plain">{{ xplStatusText(row.push_status) }}</el-tag></template></el-table-column>
    <el-table-column label="Worker" min-width="132"><template #default="{ row }"><el-tooltip :content="row.locked_by || '-'" placement="top"><span>{{ shortIdentifier(row.locked_by) }}</span></el-tooltip></template></el-table-column>
    <el-table-column label="创建时间" width="180"><template #default="{ row }">{{ formatDateTime(row.created_at) }}</template></el-table-column>
    <el-table-column label="开始时间" width="180"><template #default="{ row }">{{ formatDateTime(row.started_at) }}</template></el-table-column>
    <el-table-column label="完成时间" width="180"><template #default="{ row }">{{ formatDateTime(row.finished_at) }}</template></el-table-column>
    <el-table-column label="错误摘要" min-width="210"><template #default="{ row }"><el-tooltip v-if="row.error_message" :content="row.error_message" placement="top"><span class="xpl-job-table__error">{{ row.error_message }}</span></el-tooltip><span v-else>-</span></template></el-table-column>
    <el-table-column fixed="right" label="操作" width="90"><template #default="{ row }"><div class="xpl-job-table__actions"><el-button v-if="canRetry && (row.status === 'error' || row.status === 'retrying')" link type="primary" :icon="RefreshRight" @click="emit('retry', row)">重试</el-button></div></template></el-table-column>
  </el-table>
</template>

<style scoped>
.xpl-job-table { width: 100%; }.xpl-job-table__error { display: block; overflow: hidden; color: var(--admin-danger); text-overflow: ellipsis; white-space: nowrap; }
.xpl-job-table__actions { display: flex; align-items: center; min-width: max-content; white-space: nowrap; }
</style>

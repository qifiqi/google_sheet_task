<template>
  <div class="app-page task-create-dispatch">
    <div v-loading="!errorMsg" class="task-create-dispatch__body">
      <template v-if="errorMsg">
        <el-result icon="error" title="任务版本解析失败" :sub-title="errorMsg">
          <template #extra>
            <el-button type="primary" @click="$router.replace('/task/create/c3')">
              前往 C3 创建页
            </el-button>
          </template>
        </el-result>
      </template>
    </div>
  </div>
</template>

<script setup>
// 创建分发器（对齐 static/js/pages/google_sheet_create_dispatcher.js）：
// /task/create?restart_task_id=…（无 version）由此页查任务补 version 后重定向；
// 有 version 时直接跳对应创建页并透传其余 query 参数。
// 映射关系原文抄自静态 dispatcher（对应 app/routes/google_sheet.py::_version_from_task_type）。
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getTask } from '@/api/task'

const route = useRoute()
const router = useRouter()
const errorMsg = ref('')

const KNOWN_VERSIONS = ['c3', 'c4', 'c5', 'c7', 'c31']

function taskTypeToVersion(taskType) {
  const normalized = String(taskType || '').toLowerCase()
  if (normalized === 'google_sheet_c5') return 'c5'
  if (normalized === 'google_sheet_c7') return 'c7'
  if (normalized === 'google_sheet_c4') return 'c4'
  if (normalized === 'google_sheet') return 'c3'
  return null
}

function redirectToCreate(version, query) {
  router.replace({ path: `/task/create/${version || 'c3'}`, query })
}

onMounted(async () => {
  const { version, restart_task_id, task_id, ...rest } = route.query
  const restartId = restart_task_id || task_id

  // 有 version：直接跳对应创建页，透传其余参数（restart_task_id 归一为 restart_task_id）
  if (version && KNOWN_VERSIONS.includes(String(version))) {
    redirectToCreate(String(version), {
      ...rest,
      ...(restartId ? { restart_task_id: restartId } : {})
    })
    return
  }

  if (!restartId) {
    // 无可解析参数：落回默认 C3 创建页（与静态版缺省分支一致）
    redirectToCreate('c3', {})
    return
  }

  try {
    const res = await getTask(restartId)
    const task = res.task || res
    const mapped = taskTypeToVersion(task?.task_type)
    if (mapped) {
      redirectToCreate(mapped, { ...rest, restart_task_id: restartId })
    } else {
      // 未知类型/任务：落回默认 C3 创建页（静态缺省分支），保留 restart 参数
      redirectToCreate('c3', { ...rest, restart_task_id: restartId })
    }
  } catch (e) {
    errorMsg.value = e?.message || '加载原任务失败，请从任务列表重试'
  }
})
</script>

<style scoped>
.task-create-dispatch {
  min-height: 100%;
}

.task-create-dispatch__body {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}
</style>

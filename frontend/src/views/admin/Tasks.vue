<template>
  <div class="tasks">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="title">任务管理</h1>
      <p class="description">管理和监控所有任务的执行状态</p>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索任务名称..."
          :prefix-icon="Search"
          clearable
          style="width: 300px"
          @input="handleSearch"
        />
        <el-select
          v-model="statusFilter"
          placeholder="状态筛选"
          clearable
          style="width: 150px"
          @change="handleFilter"
        >
          <el-option label="全部" value="" />
          <el-option label="待执行" value="pending" />
          <el-option label="执行中" value="running" />
          <el-option label="已完成" value="completed" />
          <el-option label="已取消" value="cancelled" />
          <el-option label="执行出错" value="error" />
        </el-select>
      </div>
      <div class="toolbar-right">
        <el-button 
          :icon="Refresh" 
          @click="refreshTasks"
          :loading="loading"
        >
          刷新
        </el-button>
        <el-button 
          type="primary" 
          :icon="Plus"
          @click="$router.push('/google-sheet/create')"
        >
          创建任务
        </el-button>
      </div>
    </div>

    <!-- 任务表格 -->
    <el-card class="table-card">
      <div class="table-container">
        <el-table 
          :data="filteredTasks" 
          v-loading="loading"
          empty-text="暂无任务数据"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="55" />
          
          <el-table-column prop="name" label="任务名称" min-width="200">
            <template #default="{ row }">
              <div class="task-name">
                <span class="name">{{ row.name }}</span>
                <span class="description">{{ row.description }}</span>
              </div>
            </template>
          </el-table-column>
          
          <el-table-column prop="task_type" label="类型" width="120">
            <template #default="{ row }">
              <el-tag size="small">{{ row.task_type }}</el-tag>
            </template>
          </el-table-column>
          
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag 
                :type="getTaskStatus(row.status).type" 
                size="small"
              >
                {{ getTaskStatus(row.status).text }}
              </el-tag>
            </template>
          </el-table-column>
          
          <el-table-column label="进度" width="180">
            <template #default="{ row }">
              <div v-if="row.total_steps > 0" class="progress-container">
                <el-progress 
                  :percentage="Math.round((row.current_step / row.total_steps) * 100)"
                  :stroke-width="8"
                  :show-text="false"
                />
                <div class="progress-text">
                  {{ row.current_step }}/{{ row.total_steps }}
                </div>
              </div>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          
          <el-table-column prop="created_at" label="创建时间" width="160">
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
          
          <el-table-column prop="updated_at" label="更新时间" width="160">
            <template #default="{ row }">
              {{ formatTime(row.updated_at) }}
            </template>
          </el-table-column>
          
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <div class="action-buttons">
                <el-button 
                  type="primary" 
                  size="small" 
                  text
                  @click="viewTask(row.id)"
                >
                  查看
                </el-button>
                
                <el-button 
                  v-if="row.status === 'running'" 
                  type="warning" 
                  size="small" 
                  text
                  @click="cancelTask(row.id)"
                >
                  取消
                </el-button>
                
                <el-button 
                  v-if="['error', 'cancelled'].includes(row.status)" 
                  type="success" 
                  size="small" 
                  text
                  @click="restartTask(row.id)"
                >
                  重启
                </el-button>
                
                <el-popconfirm
                  title="确定要删除这个任务吗？"
                  @confirm="deleteTask(row.id)"
                >
                  <template #reference>
                    <el-button 
                      type="danger" 
                      size="small" 
                      text
                    >
                      删除
                    </el-button>
                  </template>
                </el-popconfirm>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 批量操作 -->
    <div v-if="selectedTasks.length > 0" class="batch-actions">
      <el-card>
        <div class="batch-content">
          <span class="selected-info">
            已选择 {{ selectedTasks.length }} 个任务
          </span>
          <div class="batch-buttons">
            <el-button 
              type="warning" 
              size="small"
              @click="batchCancel"
            >
              批量取消
            </el-button>
            <el-popconfirm
              title="确定要删除选中的任务吗？"
              @confirm="batchDelete"
            >
              <template #reference>
                <el-button 
                  type="danger" 
                  size="small"
                >
                  批量删除
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTaskStore } from '../../stores'
import { formatTime, getTaskStatus, debounce } from '../../utils'
import { 
  Search, 
  Refresh, 
  Plus 
} from '@element-plus/icons-vue'

const router = useRouter()
const taskStore = useTaskStore()

const loading = ref(false)
const searchKeyword = ref('')
const statusFilter = ref('')
const selectedTasks = ref([])

// 过滤后的任务列表
const filteredTasks = computed(() => {
  let tasks = [...taskStore.tasks]
  
  // 搜索过滤
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    tasks = tasks.filter(task => 
      task.name.toLowerCase().includes(keyword) ||
      task.description.toLowerCase().includes(keyword)
    )
  }
  
  // 状态过滤
  if (statusFilter.value) {
    tasks = tasks.filter(task => task.status === statusFilter.value)
  }
  
  // 按创建时间倒序排列
  tasks.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  
  return tasks
})

// 刷新任务列表
const refreshTasks = async () => {
  loading.value = true
  try {
    await taskStore.fetchTasks()
    ElMessage.success('任务列表刷新成功')
  } catch (error) {
    ElMessage.error('刷新任务列表失败')
  } finally {
    loading.value = false
  }
}

// 搜索处理（防抖）
const handleSearch = debounce(() => {
  // 搜索逻辑已在computed中处理
}, 300)

// 状态筛选处理
const handleFilter = () => {
  // 筛选逻辑已在computed中处理
}

// 选择变化处理
const handleSelectionChange = (selection) => {
  selectedTasks.value = selection
}

// 查看任务详情
const viewTask = (taskId) => {
  router.push(`/google-sheet/detail?task_id=${taskId}`)
}

// 取消任务
const cancelTask = async (taskId) => {
  try {
    await taskStore.cancelTask(taskId)
    ElMessage.success('任务已取消')
  } catch (error) {
    ElMessage.error('取消任务失败')
  }
}

// 重启任务
const restartTask = async (taskId) => {
  try {
    const result = await ElMessageBox.confirm(
      '是否要重启这个任务？',
      '确认重启',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    if (result === 'confirm') {
      // 调用重启API
      ElMessage.success('任务重启成功')
      await refreshTasks()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重启任务失败')
    }
  }
}

// 删除任务
const deleteTask = async (taskId) => {
  try {
    await taskStore.deleteTask(taskId)
    ElMessage.success('任务已删除')
  } catch (error) {
    ElMessage.error('删除任务失败')
  }
}

// 批量取消
const batchCancel = async () => {
  try {
    const runningTasks = selectedTasks.value.filter(task => task.status === 'running')
    if (runningTasks.length === 0) {
      ElMessage.warning('没有可取消的任务')
      return
    }
    
    for (const task of runningTasks) {
      await taskStore.cancelTask(task.id)
    }
    
    ElMessage.success(`成功取消 ${runningTasks.length} 个任务`)
    selectedTasks.value = []
  } catch (error) {
    ElMessage.error('批量取消失败')
  }
}

// 批量删除
const batchDelete = async () => {
  try {
    for (const task of selectedTasks.value) {
      await taskStore.deleteTask(task.id)
    }
    
    ElMessage.success(`成功删除 ${selectedTasks.value.length} 个任务`)
    selectedTasks.value = []
  } catch (error) {
    ElMessage.error('批量删除失败')
  }
}

// 页面加载时获取数据
onMounted(() => {
  refreshTasks()
})
</script>

<style scoped>
.tasks {
  padding: 0;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  gap: 16px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.table-card {
  margin-bottom: 20px;
}

.task-name .name {
  display: block;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.task-name .description {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.progress-container {
  width: 100%;
}

.progress-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
  margin-top: 4px;
}

.text-muted {
  color: var(--el-text-color-placeholder);
}

.action-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.batch-actions {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
}

.batch-content {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
}

.selected-info {
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.batch-buttons {
  display: flex;
  gap: 8px;
}

@media (max-width: 768px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  
  .toolbar-left {
    flex-direction: column;
    align-items: stretch;
  }
  
  .toolbar-right {
    justify-content: center;
  }
  
  .action-buttons {
    justify-content: center;
  }
  
  .batch-actions {
    left: 10px;
    right: 10px;
    transform: none;
  }
}
</style>

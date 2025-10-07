import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../utils/api'

// 主应用状态管理
export const useAppStore = defineStore('app', () => {
  // 状态
  const loading = ref(false)
  const sidebarCollapsed = ref(false)
  const theme = ref('light')
  
  // 计算属性
  const isLoading = computed(() => loading.value)
  
  // 方法
  const setLoading = (value) => {
    loading.value = value
  }
  
  const toggleSidebar = () => {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }
  
  const setSidebarCollapsed = (value) => {
    sidebarCollapsed.value = value
  }
  
  const setTheme = (newTheme) => {
    theme.value = newTheme
  }
  
  return {
    loading,
    sidebarCollapsed,
    theme,
    isLoading,
    setLoading,
    toggleSidebar,
    setSidebarCollapsed,
    setTheme
  }
})

// 任务管理状态
export const useTaskStore = defineStore('task', () => {
  const tasks = ref([])
  const currentTask = ref(null)
  const taskLogs = ref([])
  const taskResults = ref([])
  
  // 获取所有任务
  const fetchTasks = async () => {
    try {
      const response = await api.get('/tasks')
      if (response.data.status === 'success') {
        tasks.value = response.data.tasks
      }
      return response.data
    } catch (error) {
      console.error('获取任务列表失败:', error)
      throw error
    }
  }
  
  // 获取任务详情
  const fetchTask = async (taskId) => {
    try {
      const response = await api.get(`/tasks/${taskId}`)
      if (response.data.status === 'success') {
        currentTask.value = response.data.task
      }
      return response.data
    } catch (error) {
      console.error('获取任务详情失败:', error)
      throw error
    }
  }
  
  // 创建任务
  const createTask = async (taskData) => {
    try {
      const response = await api.post('/tasks', taskData)
      if (response.data.status === 'success') {
        await fetchTasks() // 刷新任务列表
      }
      return response.data
    } catch (error) {
      console.error('创建任务失败:', error)
      throw error
    }
  }
  
  // 取消任务
  const cancelTask = async (taskId) => {
    try {
      const response = await api.post(`/tasks/${taskId}/cancel`)
      if (response.data.status === 'success') {
        await fetchTasks() // 刷新任务列表
      }
      return response.data
    } catch (error) {
      console.error('取消任务失败:', error)
      throw error
    }
  }
  
  // 删除任务
  const deleteTask = async (taskId) => {
    try {
      const response = await api.delete(`/tasks/${taskId}`)
      if (response.data.status === 'success') {
        await fetchTasks() // 刷新任务列表
      }
      return response.data
    } catch (error) {
      console.error('删除任务失败:', error)
      throw error
    }
  }
  
  // 获取任务日志
  const fetchTaskLogs = async (taskId) => {
    try {
      const response = await api.get(`/tasks/${taskId}/logs`)
      if (response.data.status === 'success') {
        taskLogs.value = response.data.logs
      }
      return response.data
    } catch (error) {
      console.error('获取任务日志失败:', error)
      throw error
    }
  }
  
  // 获取任务结果
  const fetchTaskResults = async (taskId) => {
    try {
      const response = await api.get(`/tasks/${taskId}/results`)
      if (response.data.status === 'success') {
        taskResults.value = response.data.results
      }
      return response.data
    } catch (error) {
      console.error('获取任务结果失败:', error)
      throw error
    }
  }
  
  return {
    tasks,
    currentTask,
    taskLogs,
    taskResults,
    fetchTasks,
    fetchTask,
    createTask,
    cancelTask,
    deleteTask,
    fetchTaskLogs,
    fetchTaskResults
  }
})

// 配置管理状态
export const useConfigStore = defineStore('config', () => {
  const config = ref({})
  const googleSheetConfig = ref({})
  
  // 获取系统配置
  const fetchConfig = async () => {
    try {
      const response = await api.get('/config')
      if (response.data.status === 'success') {
        config.value = response.data.config
      }
      return response.data
    } catch (error) {
      console.error('获取系统配置失败:', error)
      throw error
    }
  }
  
  // 更新系统配置
  const updateConfig = async (configData) => {
    try {
      const response = await api.post('/config', configData)
      if (response.data.status === 'success') {
        await fetchConfig() // 刷新配置
      }
      return response.data
    } catch (error) {
      console.error('更新系统配置失败:', error)
      throw error
    }
  }
  
  // 获取Google Sheet配置
  const fetchGoogleSheetConfig = async () => {
    try {
      const response = await api.get('/config/google-sheet')
      if (response.data.status === 'success') {
        googleSheetConfig.value = response.data.config
      }
      return response.data
    } catch (error) {
      console.error('获取Google Sheet配置失败:', error)
      throw error
    }
  }
  
  // 更新Google Sheet配置
  const updateGoogleSheetConfig = async (configData) => {
    try {
      const response = await api.post('/config/google-sheet', configData)
      if (response.data.status === 'success') {
        await fetchGoogleSheetConfig() // 刷新配置
      }
      return response.data
    } catch (error) {
      console.error('更新Google Sheet配置失败:', error)
      throw error
    }
  }
  
  return {
    config,
    googleSheetConfig,
    fetchConfig,
    updateConfig,
    fetchGoogleSheetConfig,
    updateGoogleSheetConfig
  }
})

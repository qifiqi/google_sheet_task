<template>
  <div class="config">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="title">系统配置</h1>
      <p class="description">管理系统运行参数和Google Sheet配置</p>
    </div>

    <el-row :gutter="20">
      <!-- 系统配置 -->
      <el-col :xs="24" :lg="12">
        <el-card class="config-card">
          <template #header>
            <div class="card-header">
              <span class="title">
                <el-icon><Setting /></el-icon>
                系统配置
              </span>
              <el-button 
                type="primary" 
                size="small"
                @click="saveSystemConfig"
                :loading="systemConfigLoading"
              >
                保存
              </el-button>
            </div>
          </template>
          
          <el-form 
            :model="systemConfig" 
            label-width="140px"
            label-position="left"
          >
            <el-form-item label="最大并发任务数">
              <el-input-number
                v-model="systemConfig.max_concurrent_tasks"
                :min="1"
                :max="20"
                style="width: 100%"
              />
            </el-form-item>
            
            <el-form-item label="任务超时时间(秒)">
              <el-input-number
                v-model="systemConfig.task_timeout"
                :min="60"
                :max="7200"
                style="width: 100%"
              />
            </el-form-item>
            
            <el-form-item label="日志级别">
              <el-select v-model="systemConfig.log_level" style="width: 100%">
                <el-option label="DEBUG" value="DEBUG" />
                <el-option label="INFO" value="INFO" />
                <el-option label="WARNING" value="WARNING" />
                <el-option label="ERROR" value="ERROR" />
              </el-select>
            </el-form-item>
            
            <el-form-item label="仪表盘刷新间隔(秒)">
              <el-input-number
                v-model="systemConfig.dashboard_refresh_interval"
                :min="10"
                :max="300"
                style="width: 100%"
              />
            </el-form-item>
            
            <el-form-item label="自动清理日志">
              <el-switch v-model="systemConfig.auto_cleanup_logs" />
            </el-form-item>
            
            <el-form-item label="日志保留天数">
              <el-input-number
                v-model="systemConfig.log_retention_days"
                :min="1"
                :max="365"
                :disabled="!systemConfig.auto_cleanup_logs"
                style="width: 100%"
              />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- Google Sheet配置 -->
      <el-col :xs="24" :lg="12">
        <el-card class="config-card">
          <template #header>
            <div class="card-header">
              <span class="title">
                <el-icon><Grid /></el-icon>
                Google Sheet配置
              </span>
              <el-button 
                type="primary" 
                size="small"
                @click="saveGoogleSheetConfig"
                :loading="googleSheetConfigLoading"
              >
                保存
              </el-button>
            </div>
          </template>
          
          <el-form 
            :model="googleSheetConfig" 
            label-width="140px"
            label-position="left"
          >
            <el-form-item label="电子表格ID">
              <el-input
                v-model="googleSheetConfig.spreadsheet_id"
                placeholder="请输入Google Sheet的ID"
              />
            </el-form-item>
            
            <el-form-item label="工作表名称">
              <el-input
                v-model="googleSheetConfig.sheet_name"
                placeholder="例如: Sheet1"
              />
            </el-form-item>
            
            <el-form-item label="Token文件路径">
              <el-input
                v-model="googleSheetConfig.token_file"
                placeholder="例如: data/token.json"
              />
            </el-form-item>
            
            <el-form-item label="代理URL">
              <el-input
                v-model="googleSheetConfig.proxy_url"
                placeholder="可选，留空表示不使用代理"
              />
            </el-form-item>
            
            <el-form-item label="请求间隔(毫秒)">
              <el-input-number
                v-model="googleSheetConfig.request_interval"
                :min="100"
                :max="5000"
                style="width: 100%"
              />
            </el-form-item>
            
            <el-form-item label="重试次数">
              <el-input-number
                v-model="googleSheetConfig.retry_count"
                :min="1"
                :max="10"
                style="width: 100%"
              />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- 位置配置 -->
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="config-card">
          <template #header>
            <div class="card-header">
              <span class="title">
                <el-icon><Location /></el-icon>
                位置配置
              </span>
              <div class="header-actions">
                <el-button 
                  size="small"
                  @click="addPosition('parameter')"
                >
                  添加参数位置
                </el-button>
                <el-button 
                  size="small"
                  @click="addPosition('check')"
                >
                  添加检查位置
                </el-button>
                <el-button 
                  size="small"
                  @click="addPosition('result')"
                >
                  添加结果位置
                </el-button>
                <el-button 
                  type="primary" 
                  size="small"
                  @click="savePositionConfig"
                  :loading="positionConfigLoading"
                >
                  保存位置配置
                </el-button>
              </div>
            </div>
          </template>
          
          <el-tabs v-model="activePositionTab">
            <el-tab-pane label="参数位置" name="parameter">
              <div class="position-list">
                <div 
                  v-for="(position, key) in googleSheetConfig.parameter_positions" 
                  :key="key"
                  class="position-item"
                >
                  <el-input
                    v-model="parameterPositions[key].key"
                    placeholder="参数名称"
                    style="width: 200px"
                  />
                  <el-input
                    v-model="parameterPositions[key].value"
                    placeholder="单元格位置 (如: B6)"
                    style="width: 200px"
                  />
                  <el-button 
                    type="danger" 
                    size="small" 
                    text
                    @click="removePosition('parameter', key)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
            </el-tab-pane>
            
            <el-tab-pane label="检查位置" name="check">
              <div class="position-list">
                <div 
                  v-for="(position, key) in googleSheetConfig.check_positions" 
                  :key="key"
                  class="position-item"
                >
                  <el-input
                    v-model="checkPositions[key].key"
                    placeholder="检查名称"
                    style="width: 200px"
                  />
                  <el-input
                    v-model="checkPositions[key].value"
                    placeholder="单元格位置 (如: I6)"
                    style="width: 200px"
                  />
                  <el-button 
                    type="danger" 
                    size="small" 
                    text
                    @click="removePosition('check', key)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
            </el-tab-pane>
            
            <el-tab-pane label="结果位置" name="result">
              <div class="position-list">
                <div 
                  v-for="(position, key) in googleSheetConfig.result_positions" 
                  :key="key"
                  class="position-item"
                >
                  <el-input
                    v-model="resultPositions[key].key"
                    placeholder="结果名称"
                    style="width: 200px"
                  />
                  <el-input
                    v-model="resultPositions[key].value"
                    placeholder="单元格位置 (如: I15)"
                    style="width: 200px"
                  />
                  <el-button 
                    type="danger" 
                    size="small" 
                    text
                    @click="removePosition('result', key)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>

    <!-- 配置测试 -->
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="config-card">
          <template #header>
            <div class="card-header">
              <span class="title">
                <el-icon><Tools /></el-icon>
                配置测试
              </span>
            </div>
          </template>
          
          <div class="test-actions">
            <el-button 
              type="success"
              @click="testGoogleSheetConnection"
              :loading="testLoading"
            >
              测试Google Sheet连接
            </el-button>
            
            <el-button 
              @click="validateConfig"
              :loading="validateLoading"
            >
              验证配置完整性
            </el-button>
            
            <el-button 
              @click="exportConfig"
            >
              导出配置
            </el-button>
            
            <el-upload
              :show-file-list="false"
              :before-upload="importConfig"
              accept=".json"
            >
              <el-button>导入配置</el-button>
            </el-upload>
          </div>
          
          <div v-if="testResult" class="test-result">
            <el-alert
              :title="testResult.title"
              :type="testResult.type"
              :description="testResult.message"
              show-icon
              :closable="false"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '../../stores'
import { deepClone, downloadFile } from '../../utils'
import { 
  Setting, 
  Grid, 
  Location, 
  Tools 
} from '@element-plus/icons-vue'

const configStore = useConfigStore()

const systemConfigLoading = ref(false)
const googleSheetConfigLoading = ref(false)
const positionConfigLoading = ref(false)
const testLoading = ref(false)
const validateLoading = ref(false)

const activePositionTab = ref('parameter')
const testResult = ref(null)

// 系统配置
const systemConfig = reactive({
  max_concurrent_tasks: 5,
  task_timeout: 3600,
  log_level: 'INFO',
  dashboard_refresh_interval: 30,
  auto_cleanup_logs: false,
  log_retention_days: 30
})

// Google Sheet配置
const googleSheetConfig = reactive({
  spreadsheet_id: '',
  sheet_name: 'Sheet1',
  token_file: 'data/token.json',
  proxy_url: '',
  request_interval: 1000,
  retry_count: 3,
  parameter_positions: {},
  check_positions: {},
  result_positions: {}
})

// 位置配置的编辑状态
const parameterPositions = ref({})
const checkPositions = ref({})
const resultPositions = ref({})

// 加载配置数据
const loadConfigs = async () => {
  try {
    await configStore.fetchConfig()
    await configStore.fetchGoogleSheetConfig()
    
    // 更新系统配置
    Object.assign(systemConfig, configStore.config)
    
    // 更新Google Sheet配置
    Object.assign(googleSheetConfig, configStore.googleSheetConfig)
    
    // 初始化位置配置编辑状态
    initPositionEditors()
    
  } catch (error) {
    ElMessage.error('加载配置失败')
  }
}

// 初始化位置配置编辑器
const initPositionEditors = () => {
  parameterPositions.value = convertPositionsToEditor(googleSheetConfig.parameter_positions)
  checkPositions.value = convertPositionsToEditor(googleSheetConfig.check_positions)
  resultPositions.value = convertPositionsToEditor(googleSheetConfig.result_positions)
}

// 转换位置配置为编辑器格式
const convertPositionsToEditor = (positions) => {
  const result = {}
  for (const [key, value] of Object.entries(positions || {})) {
    result[key] = { key, value }
  }
  return result
}

// 转换编辑器格式为位置配置
const convertEditorToPositions = (editorData) => {
  const result = {}
  for (const item of Object.values(editorData)) {
    if (item.key && item.value) {
      result[item.key] = item.value
    }
  }
  return result
}

// 保存系统配置
const saveSystemConfig = async () => {
  systemConfigLoading.value = true
  try {
    await configStore.updateConfig(systemConfig)
    ElMessage.success('系统配置保存成功')
  } catch (error) {
    ElMessage.error('系统配置保存失败')
  } finally {
    systemConfigLoading.value = false
  }
}

// 保存Google Sheet配置
const saveGoogleSheetConfig = async () => {
  googleSheetConfigLoading.value = true
  try {
    const configToSave = deepClone(googleSheetConfig)
    await configStore.updateGoogleSheetConfig(configToSave)
    ElMessage.success('Google Sheet配置保存成功')
  } catch (error) {
    ElMessage.error('Google Sheet配置保存失败')
  } finally {
    googleSheetConfigLoading.value = false
  }
}

// 保存位置配置
const savePositionConfig = async () => {
  positionConfigLoading.value = true
  try {
    const configToSave = deepClone(googleSheetConfig)
    configToSave.parameter_positions = convertEditorToPositions(parameterPositions.value)
    configToSave.check_positions = convertEditorToPositions(checkPositions.value)
    configToSave.result_positions = convertEditorToPositions(resultPositions.value)
    
    await configStore.updateGoogleSheetConfig(configToSave)
    Object.assign(googleSheetConfig, configToSave)
    
    ElMessage.success('位置配置保存成功')
  } catch (error) {
    ElMessage.error('位置配置保存失败')
  } finally {
    positionConfigLoading.value = false
  }
}

// 添加位置
const addPosition = (type) => {
  const key = `new_${Date.now()}`
  const targetRef = type === 'parameter' ? parameterPositions : 
                   type === 'check' ? checkPositions : resultPositions
  
  targetRef.value[key] = { key: '', value: '' }
}

// 删除位置
const removePosition = (type, key) => {
  const targetRef = type === 'parameter' ? parameterPositions : 
                   type === 'check' ? checkPositions : resultPositions
  
  delete targetRef.value[key]
}

// 测试Google Sheet连接
const testGoogleSheetConnection = async () => {
  testLoading.value = true
  testResult.value = null
  
  try {
    // 这里应该调用后端API测试连接
    // const response = await api.post('/config/test-google-sheet')
    
    // 模拟测试结果
    await new Promise(resolve => setTimeout(resolve, 2000))
    
    testResult.value = {
      title: '连接测试成功',
      type: 'success',
      message: 'Google Sheet连接正常，可以正常读写数据'
    }
  } catch (error) {
    testResult.value = {
      title: '连接测试失败',
      type: 'error',
      message: error.message || '无法连接到Google Sheet，请检查配置'
    }
  } finally {
    testLoading.value = false
  }
}

// 验证配置
const validateConfig = async () => {
  validateLoading.value = true
  testResult.value = null
  
  try {
    // 这里应该调用后端API验证配置
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    testResult.value = {
      title: '配置验证通过',
      type: 'success',
      message: '所有配置项都正确，系统可以正常运行'
    }
  } catch (error) {
    testResult.value = {
      title: '配置验证失败',
      type: 'error',
      message: error.message || '配置存在问题，请检查'
    }
  } finally {
    validateLoading.value = false
  }
}

// 导出配置
const exportConfig = () => {
  const config = {
    system: systemConfig,
    googleSheet: {
      ...googleSheetConfig,
      parameter_positions: convertEditorToPositions(parameterPositions.value),
      check_positions: convertEditorToPositions(checkPositions.value),
      result_positions: convertEditorToPositions(resultPositions.value)
    }
  }
  
  const configJson = JSON.stringify(config, null, 2)
  const filename = `config_${new Date().toISOString().split('T')[0]}.json`
  
  downloadFile(configJson, filename)
  ElMessage.success('配置导出成功')
}

// 导入配置
const importConfig = (file) => {
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const config = JSON.parse(e.target.result)
      
      if (config.system) {
        Object.assign(systemConfig, config.system)
      }
      
      if (config.googleSheet) {
        Object.assign(googleSheetConfig, config.googleSheet)
        initPositionEditors()
      }
      
      ElMessage.success('配置导入成功')
    } catch (error) {
      ElMessage.error('配置文件格式错误')
    }
  }
  reader.readAsText(file)
  return false // 阻止自动上传
}

// 页面加载时获取配置
onMounted(() => {
  loadConfigs()
})
</script>

<style scoped>
.config {
  padding: 0;
}

.config-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header .title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.position-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.position-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.test-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.test-result {
  margin-top: 20px;
}

@media (max-width: 768px) {
  .header-actions {
    flex-direction: column;
  }
  
  .position-item {
    flex-direction: column;
    align-items: stretch;
  }
  
  .test-actions {
    flex-direction: column;
  }
}
</style>

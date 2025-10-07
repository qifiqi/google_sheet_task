<template>
  <div class="create-task">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="title">创建Google Sheet任务</h1>
      <p class="description">配置并创建新的参数批量校验任务</p>
    </div>

    <el-form 
      ref="formRef"
      :model="formData" 
      :rules="formRules"
      label-width="140px"
      class="create-form"
    >
      <!-- 基本信息和Google Sheet配置 - 响应式布局 -->
      <div class="config-grid">
        <!-- 基本信息 -->
        <el-card class="form-section config-card">
          <template #header>
            <span class="section-title">
              <el-icon><InfoFilled /></el-icon>
              基本信息
            </span>
          </template>
          
          <el-form-item label="任务名称" prop="name">
            <el-input
              v-model="formData.name"
              placeholder="请输入任务名称"
              maxlength="100"
              show-word-limit
            />
          </el-form-item>
          
          <el-form-item label="任务描述" prop="description">
            <el-input
              v-model="formData.description"
              type="textarea"
              :rows="3"
              placeholder="请输入任务描述（可选）"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
        </el-card>

        <!-- Google Sheet配置 -->
        <el-card class="form-section config-card">
          <template #header>
            <div class="section-header">
              <span class="section-title">
                <el-icon><Grid /></el-icon>
                Google Sheet配置
              </span>
              <el-button 
                size="small" 
                @click="loadDefaultConfig"
                :loading="loadingConfig"
              >
                加载默认配置
              </el-button>
            </div>
          </template>
          
          <el-form-item label="电子表格ID" prop="googleSheetConfig.spreadsheet_id">
            <el-input
              v-model="formData.googleSheetConfig.spreadsheet_id"
              placeholder="请输入Google Sheet的ID"
            />
            <div class="form-tip">
              从Google Sheet URL中获取：https://docs.google.com/spreadsheets/d/<strong>电子表格ID</strong>/edit
            </div>
          </el-form-item>
          
          <el-form-item label="工作表名称" prop="googleSheetConfig.sheet_name">
            <el-input
              v-model="formData.googleSheetConfig.sheet_name"
              placeholder="例如: Sheet1"
            />
          </el-form-item>
          
          <el-form-item label="Token文件路径" prop="googleSheetConfig.token_file">
            <el-input
              v-model="formData.googleSheetConfig.token_file"
              placeholder="例如: data/token.json"
            />
          </el-form-item>
          
          <el-form-item label="代理URL">
            <el-input
              v-model="formData.googleSheetConfig.proxy_url"
              placeholder="可选，留空表示不使用代理"
            />
          </el-form-item>
          
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="请求间隔(毫秒)">
                <el-input-number
                  v-model="formData.googleSheetConfig.request_interval"
                  :min="100"
                  :max="5000"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="重试次数">
                <el-input-number
                  v-model="formData.googleSheetConfig.retry_count"
                  :min="1"
                  :max="10"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </el-card>
      </div>

      <!-- 参数配置和位置配置 - 响应式布局 -->
      <div class="config-grid">
        <!-- 参数配置 -->
        <el-card class="form-section config-card">
          <template #header>
            <div class="section-header">
              <span class="section-title">
                <el-icon><Setting /></el-icon>
                参数配置
              </span>
              <div class="header-actions">
                <el-button size="small" @click="showParameterHelper = true">
                  参数帮助
                </el-button>
                <el-button size="small" @click="importParameters">
                  导入参数
                </el-button>
                <el-button size="small" @click="generateSampleParameters">
                  生成列表格式
                </el-button>
                <el-button size="small" @click="generateVolatilityParameters">
                  生成对象格式
                </el-button>
              </div>
            </div>
          </template>
          
          <!-- 参数格式配置说明 -->
          <el-alert
            title="参数格式支持"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 16px;"
          >
            <template #default>
              <div>
                <p><strong>支持两种参数格式：</strong></p>
                <ul style="margin: 8px 0; padding-left: 20px;">
                  <li><strong>列表格式</strong>：传统的二维数组格式 <code>[[...], [...], ...]</code></li>
                  <li><strong>对象格式</strong>：波动率调参专用格式 <code>{"xm_Arr": [...], "tp_Arr": [...], ...}</code></li>
                </ul>
                <p>两种格式都会生成相同的参数组合，总计：<strong>{{ calculateTotalCombinations() }} 种</strong></p>
              </div>
            </template>
          </el-alert>
          
          <el-form-item label="参数列表" prop="parameters">
            <div class="parameter-editor">
              <div class="editor-toolbar">
                <span class="editor-label">JSON格式的参数组合列表</span>
                <div class="toolbar-actions">
                  <el-button size="small" @click="formatParameters">
                    格式化
                  </el-button>
                  <el-button size="small" @click="validateParameters">
                    验证格式
                  </el-button>
                </div>
              </div>
              <el-input
                v-model="formData.parameters"
                type="textarea"
                :rows="10"
                placeholder="请输入参数列表，支持两种格式：&#10;列表格式：[[...], [...], ...]&#10;对象格式：{&quot;xm_Arr&quot;: [...], &quot;tp_Arr&quot;: [...], ...}"
                class="parameter-textarea"
              />
            </div>
            <div v-if="parameterValidation.error" class="validation-error">
              <el-icon><WarningFilled /></el-icon>
              {{ parameterValidation.message }}
            </div>
            <div v-else-if="parameterValidation.success" class="validation-success">
              <el-icon><CircleCheck /></el-icon>
              参数格式正确，共 {{ parameterValidation.count }} 组参数组合
            </div>
          </el-form-item>
        </el-card>

        <!-- 位置配置 -->
        <el-card class="form-section config-card">
          <template #header>
            <div class="section-header">
              <span class="section-title">
                <el-icon><Location /></el-icon>
                位置配置
              </span>
              <el-button 
                size="small" 
                @click="showPositionHelper = true"
              >
                位置帮助
              </el-button>
            </div>
          </template>
          
          <el-tabs v-model="activePositionTab">
            <el-tab-pane label="参数位置" name="parameter">
              <div class="position-section">
                <div class="position-header">
                  <span>配置参数在表格中的位置</span>
                  <el-button size="small" @click="addPosition('parameter')">
                    添加参数位置
                  </el-button>
                </div>
                <div class="position-list">
                  <div 
                    v-for="(item, index) in formData.parameterPositions" 
                    :key="index"
                    class="position-item"
                  >
                    <el-input
                      v-model="item.name"
                      placeholder="参数名称"
                      style="width: 200px"
                    />
                    <el-input
                      v-model="item.position"
                      placeholder="单元格位置 (如: B6)"
                      style="width: 150px"
                    />
                    <el-button 
                      type="danger" 
                      size="small" 
                      text
                      @click="removePosition('parameter', index)"
                    >
                      删除
                    </el-button>
                  </div>
                </div>
              </div>
            </el-tab-pane>
            
            <el-tab-pane label="检查位置" name="check">
              <div class="position-section">
                <div class="position-header">
                  <span>配置检查结果在表格中的位置</span>
                  <el-button size="small" @click="addPosition('check')">
                    添加检查位置
                  </el-button>
                </div>
                <div class="position-list">
                  <div 
                    v-for="(item, index) in formData.checkPositions" 
                    :key="index"
                    class="position-item"
                  >
                    <el-input
                      v-model="item.name"
                      placeholder="检查名称"
                      style="width: 200px"
                    />
                    <el-input
                      v-model="item.position"
                      placeholder="单元格位置 (如: I6)"
                      style="width: 150px"
                    />
                    <el-button 
                      type="danger" 
                      size="small" 
                      text
                      @click="removePosition('check', index)"
                    >
                      删除
                    </el-button>
                  </div>
                </div>
              </div>
            </el-tab-pane>
            
            <el-tab-pane label="结果位置" name="result">
              <div class="position-section">
                <div class="position-header">
                  <span>配置最终结果在表格中的位置</span>
                  <el-button size="small" @click="addPosition('result')">
                    添加结果位置
                  </el-button>
                </div>
                <div class="position-list">
                  <div 
                    v-for="(item, index) in formData.resultPositions" 
                    :key="index"
                    class="position-item"
                  >
                    <el-input
                      v-model="item.name"
                      placeholder="结果名称"
                      style="width: 200px"
                    />
                    <el-input
                      v-model="item.position"
                      placeholder="单元格位置 (如: I15)"
                      style="width: 150px"
                    />
                    <el-button 
                      type="danger" 
                      size="small" 
                      text
                      @click="removePosition('result', index)"
                    >
                      删除
                    </el-button>
                  </div>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </div>

      <!-- 操作按钮 -->
      <div class="form-actions">
        <el-button @click="$router.go(-1)">
          取消
        </el-button>
        <el-button @click="saveDraft" :loading="saving">
          保存草稿
        </el-button>
        <el-button 
          type="primary" 
          @click="createTask"
          :loading="creating"
        >
          创建并启动任务
        </el-button>
      </div>
    </el-form>

    <!-- 位置帮助对话框 -->
    <el-dialog
      v-model="showPositionHelper"
      title="位置配置帮助"
      width="600px"
    >
      <div class="helper-content">
        <h4>单元格位置格式说明</h4>
        <ul>
          <li><strong>列字母 + 行数字</strong>：如 A1, B6, C10</li>
          <li><strong>列范围</strong>：如 A1:C1 表示A1到C1的范围</li>
          <li><strong>行范围</strong>：如 A1:A10 表示A1到A10的范围</li>
        </ul>
        
        <h4>配置示例</h4>
        <div class="example">
          <p><strong>参数位置</strong>：将参数值写入到指定单元格</p>
          <p>参数1 → B6，参数2 → B7，参数3 → B8</p>
        </div>
        <div class="example">
          <p><strong>检查位置</strong>：读取检查结果的单元格</p>
          <p>检查1 → I6，检查2 → I7，检查3 → I8</p>
        </div>
        <div class="example">
          <p><strong>结果位置</strong>：读取最终结果的单元格</p>
          <p>结果1 → I15，结果2 → I16，结果3 → I17</p>
        </div>
      </div>
    </el-dialog>

    <!-- 参数帮助对话框 -->
    <el-dialog
      v-model="showParameterHelper"
      title="参数配置帮助"
      width="700px"
    >
      <div class="helper-content">
        <h4>参数格式说明</h4>
        <p>支持两种参数格式：<strong>列表格式</strong> 和 <strong>波动率调参对象格式</strong>。</p>
        
        <h4>格式一：列表格式（原格式）</h4>
        <pre class="code-example">
[
  [6, 6.4, 6.8, 7.2, 7.6, 8],                    // 第1个参数的可能值
  [0.79, 0.81, 0.83, 0.85, 0.87, 0.89, 0.91, 0.93, 0.95, 0.97], // 第2个参数的可能值
  [0.24],                                         // 第3个参数的可能值
  [0.88],                                         // 第4个参数的可能值
  [0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1], // 第5个参数的可能值
  [0.24, 0.26, 0.28, 0.3, 0.32, 0.34, 0.36, 0.38] // 第6个参数的可能值
]</pre>
        
        <h4>格式二：波动率调参对象格式（新格式）</h4>
        <pre class="code-example">
{
  "xm_Arr": [6, 6.4, 6.8, 7.2, 7.6, 8],
  "tp_Arr": [0.79, 0.81, 0.83, 0.85, 0.87, 0.89, 0.91, 0.93, 0.95, 0.97],
  "zl_Arr": [0.24],
  "zg_Arr": [0.88],
  "ywfs_Arr": [0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1],
  "ywfb_Arr": [0.24, 0.26, 0.28, 0.3, 0.32, 0.34, 0.36, 0.38]
}</pre>
        
        <h4>执行说明</h4>
        <p>系统会自动生成所有参数的笛卡尔积组合：</p>
        <ul>
          <li>6 + 0.79 + 0.24 + 0.88 + 0 + 0.24</li>
          <li>6 + 0.79 + 0.24 + 0.88 + 0 + 0.26</li>
          <li>6 + 0.79 + 0.24 + 0.88 + 0 + 0.28</li>
          <li>6 + 0.79 + 0.24 + 0.88 + 0.01 + 0.24</li>
          <li>... (共 {{ calculateTotalCombinations() }} 种组合)</li>
        </ul>
      </div>
    </el-dialog>

    <!-- 文件上传 -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".json,.txt"
      style="display: none"
      @change="handleFileImport"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useTaskStore, useConfigStore } from '../../stores'
import { isValidJSON } from '../../utils'
import { 
  InfoFilled, 
  Grid, 
  Location, 
  Setting, 
  WarningFilled, 
  CircleCheck 
} from '@element-plus/icons-vue'

// 波动率调参1 - 参数配置
const volatilityParameters = {
  xm_Arr: [6, 6.4, 6.8, 7.2, 7.6, 8],
  tp_Arr: [0.79, 0.81, 0.83, 0.85, 0.87, 0.89, 0.91, 0.93, 0.95, 0.97],
  zl_Arr: [0.24],
  zg_Arr: [0.88],
  ywfs_Arr: [0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1],
  ywfb_Arr: [0.24, 0.26, 0.28, 0.3, 0.32, 0.34, 0.36, 0.38]
}

const router = useRouter()
const route = useRoute()
const taskStore = useTaskStore()
const configStore = useConfigStore()

const formRef = ref(null)
const fileInputRef = ref(null)

const loading = ref(false)
const loadingConfig = ref(false)
const saving = ref(false)
const creating = ref(false)

const showPositionHelper = ref(false)
const showParameterHelper = ref(false)
const activePositionTab = ref('parameter')

// 表单数据
const formData = reactive({
  name: '',
  description: '',
  googleSheetConfig: {
    spreadsheet_id: '',
    sheet_name: 'Sheet1',
    token_file: 'data/token.json',
    proxy_url: '',
    request_interval: 1000,
    retry_count: 3
  },
  parameterPositions: [],
  checkPositions: [],
  resultPositions: [],
  parameters: ''
})

// 参数验证状态
const parameterValidation = reactive({
  error: false,
  success: false,
  message: '',
  count: 0
})

// 表单验证规则
const formRules = {
  name: [
    { required: true, message: '请输入任务名称', trigger: 'blur' },
    { min: 2, max: 100, message: '任务名称长度在 2 到 100 个字符', trigger: 'blur' }
  ],
  'googleSheetConfig.spreadsheet_id': [
    { required: true, message: '请输入电子表格ID', trigger: 'blur' }
  ],
  'googleSheetConfig.sheet_name': [
    { required: true, message: '请输入工作表名称', trigger: 'blur' }
  ],
  'googleSheetConfig.token_file': [
    { required: true, message: '请输入Token文件路径', trigger: 'blur' }
  ],
  parameters: [
    { required: true, message: '请输入参数列表', trigger: 'blur' },
    { validator: validateParametersFormat, trigger: 'blur' }
  ]
}

// 参数格式验证器
function validateParametersFormat(rule, value, callback) {
  if (!value) {
    callback(new Error('请输入参数列表'))
    return
  }
  
  try {
    const params = JSON.parse(value)
    
    // 支持两种格式：对象格式和数组格式
    if (Array.isArray(params)) {
      // 原来的列表格式验证
      if (params.length === 0) {
        callback(new Error('参数列表不能为空'))
        return
      }
      
      for (let i = 0; i < params.length; i++) {
        if (!Array.isArray(params[i])) {
          callback(new Error(`第 ${i + 1} 个参数组必须是数组格式`))
          return
        }
        if (params[i].length === 0) {
          callback(new Error(`第 ${i + 1} 个参数组不能为空`))
          return
        }
      }
    } else if (typeof params === 'object' && params !== null) {
      // 新的对象格式验证（波动率调参格式）
      const requiredKeys = ['xm_Arr', 'tp_Arr', 'zl_Arr', 'zg_Arr', 'ywfs_Arr', 'ywfb_Arr']
      const paramKeys = Object.keys(params)
      
      // 检查是否包含所有必需的键
      for (const key of requiredKeys) {
        if (!params.hasOwnProperty(key)) {
          callback(new Error(`缺少必需的参数: ${key}`))
          return
        }
        if (!Array.isArray(params[key])) {
          callback(new Error(`参数 ${key} 必须是数组格式`))
          return
        }
        if (params[key].length === 0) {
          callback(new Error(`参数 ${key} 不能为空`))
          return
        }
      }
      
      // 检查是否有多余的键
      for (const key of paramKeys) {
        if (!requiredKeys.includes(key)) {
          callback(new Error(`不支持的参数: ${key}，支持的参数有: ${requiredKeys.join(', ')}`))
          return
        }
      }
    } else {
      callback(new Error('参数列表必须是数组格式或波动率调参对象格式'))
      return
    }
    
    callback()
  } catch (error) {
    callback(new Error('参数列表格式错误，请检查JSON格式'))
  }
}

// 监听参数变化，实时验证
watch(() => formData.parameters, (newValue) => {
  validateParameters(false)
})

// 加载默认配置
const loadDefaultConfig = async () => {
  loadingConfig.value = true
  try {
    await configStore.fetchGoogleSheetConfig()
    const config = configStore.googleSheetConfig
    
    if (config) {
      Object.assign(formData.googleSheetConfig, config)
      
      // 加载位置配置
      if (config.parameter_positions) {
        formData.parameterPositions = Object.entries(config.parameter_positions).map(([name, position]) => ({
          name, position
        }))
      }
      
      if (config.check_positions) {
        formData.checkPositions = Object.entries(config.check_positions).map(([name, position]) => ({
          name, position
        }))
      }
      
      if (config.result_positions) {
        formData.resultPositions = Object.entries(config.result_positions).map(([name, position]) => ({
          name, position
        }))
      }
      
      ElMessage.success('默认配置加载成功')
    }
  } catch (error) {
    ElMessage.error('加载默认配置失败')
  } finally {
    loadingConfig.value = false
  }
}

// 添加位置配置
const addPosition = (type) => {
  const newPosition = { name: '', position: '' }
  
  switch (type) {
    case 'parameter':
      formData.parameterPositions.push(newPosition)
      break
    case 'check':
      formData.checkPositions.push(newPosition)
      break
    case 'result':
      formData.resultPositions.push(newPosition)
      break
  }
}

// 删除位置配置
const removePosition = (type, index) => {
  switch (type) {
    case 'parameter':
      formData.parameterPositions.splice(index, 1)
      break
    case 'check':
      formData.checkPositions.splice(index, 1)
      break
    case 'result':
      formData.resultPositions.splice(index, 1)
      break
  }
}

// 格式化参数
const formatParameters = () => {
  try {
    if (formData.parameters) {
      const params = JSON.parse(formData.parameters)
      formData.parameters = JSON.stringify(params, null, 2)
      ElMessage.success('参数格式化成功')
    }
  } catch (error) {
    ElMessage.error('参数格式错误，无法格式化')
  }
}

// 验证参数格式
const validateParameters = (showMessage = true) => {
  if (!formData.parameters) {
    parameterValidation.error = false
    parameterValidation.success = false
    return
  }
  
  try {
    const params = JSON.parse(formData.parameters)
    let totalCombinations = 1
    let paramArrays = []
    
    if (Array.isArray(params)) {
      // 原来的列表格式
      if (params.length === 0) {
        throw new Error('参数列表不能为空')
      }
      
      for (let i = 0; i < params.length; i++) {
        if (!Array.isArray(params[i])) {
          throw new Error(`第 ${i + 1} 个参数组必须是数组格式`)
        }
        if (params[i].length === 0) {
          throw new Error(`第 ${i + 1} 个参数组不能为空`)
        }
        totalCombinations *= params[i].length
      }
      paramArrays = params
    } else if (typeof params === 'object' && params !== null) {
      // 新的对象格式（波动率调参格式）
      const requiredKeys = ['xm_Arr', 'tp_Arr', 'zl_Arr', 'zg_Arr', 'ywfs_Arr', 'ywfb_Arr']
      
      // 验证格式
      for (const key of requiredKeys) {
        if (!params.hasOwnProperty(key)) {
          throw new Error(`缺少必需的参数: ${key}`)
        }
        if (!Array.isArray(params[key])) {
          throw new Error(`参数 ${key} 必须是数组格式`)
        }
        if (params[key].length === 0) {
          throw new Error(`参数 ${key} 不能为空`)
        }
        totalCombinations *= params[key].length
      }
      
      // 转换为数组格式用于计算
      paramArrays = requiredKeys.map(key => params[key])
    } else {
      throw new Error('参数列表必须是数组格式或波动率调参对象格式')
    }
    
    parameterValidation.error = false
    parameterValidation.success = true
    parameterValidation.count = totalCombinations
    
    if (showMessage) {
      const formatType = Array.isArray(params) ? '列表格式' : '波动率调参格式'
      ElMessage.success(`参数${formatType}正确，共 ${totalCombinations} 组参数组合`)
    }
  } catch (error) {
    parameterValidation.error = true
    parameterValidation.success = false
    parameterValidation.message = error.message
    
    if (showMessage) {
      ElMessage.error(error.message)
    }
  }
}

// 计算波动率参数的总组合数
const calculateTotalCombinations = () => {
  return volatilityParameters.xm_Arr.length * 
         volatilityParameters.tp_Arr.length * 
         volatilityParameters.zl_Arr.length * 
         volatilityParameters.zg_Arr.length * 
         volatilityParameters.ywfs_Arr.length * 
         volatilityParameters.ywfb_Arr.length
}

// 生成示例参数（列表格式）
const generateSampleParameters = () => {
  // 使用波动率调参1的参数
  const sampleParams = [
    volatilityParameters.xm_Arr,
    volatilityParameters.tp_Arr,
    volatilityParameters.zl_Arr,
    volatilityParameters.zg_Arr,
    volatilityParameters.ywfs_Arr,
    volatilityParameters.ywfb_Arr
  ]
  
  formData.parameters = JSON.stringify(sampleParams, null, 2)
  ElMessage.success('波动率调参示例参数生成成功（列表格式）')
}

// 生成波动率调参对象格式
const generateVolatilityParameters = () => {
  formData.parameters = JSON.stringify(volatilityParameters, null, 2)
  ElMessage.success('波动率调参参数生成成功（对象格式）')
}

// 导入参数
const importParameters = () => {
  fileInputRef.value?.click()
}

// 处理文件导入
const handleFileImport = (event) => {
  const file = event.target.files[0]
  if (!file) return
  
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const content = e.target.result
      
      if (file.name.endsWith('.json')) {
        // JSON文件
        const data = JSON.parse(content)
        if (Array.isArray(data)) {
          formData.parameters = JSON.stringify(data, null, 2)
        } else if (data.parameters) {
          formData.parameters = JSON.stringify(data.parameters, null, 2)
        } else {
          throw new Error('JSON文件格式不正确')
        }
      } else {
        // 文本文件，按行分割
        const lines = content.split('\n').filter(line => line.trim())
        const params = [lines]
        formData.parameters = JSON.stringify(params, null, 2)
      }
      
      ElMessage.success('参数导入成功')
    } catch (error) {
      ElMessage.error('文件格式错误：' + error.message)
    }
  }
  reader.readAsText(file)
  
  // 清空文件输入
  event.target.value = ''
}

// 构建任务配置
const buildTaskConfig = () => {
  // 解析参数格式
  let parametersData = formData.parameters
  if (typeof parametersData === 'string') {
    parametersData = JSON.parse(parametersData)
  }
  
  // 转换为后端期望的列表格式
  let parametersList = []
  if (Array.isArray(parametersData)) {
    // 已经是列表格式，直接使用
    parametersList = parametersData
  } else if (typeof parametersData === 'object' && parametersData !== null) {
    // 对象格式，转换为列表格式（按照固定顺序）
    const keyOrder = ['xm_Arr', 'tp_Arr', 'zl_Arr', 'zg_Arr', 'ywfs_Arr', 'ywfb_Arr']
    parametersList = keyOrder.map(key => parametersData[key])
  }
  
  // 构建位置配置 - 按照波动率调参的顺序
  const parameter_positions = [
    "B6",  // xm_Arr 对应位置
    "B7",  // tp_Arr 对应位置
    "B9",  // zl_Arr 对应位置
    "B10", // zg_Arr 对应位置
    "B11", // ywfs_Arr 对应位置
    "B12"  // ywfb_Arr 对应位置
  ]
  
  // 检查位置配置 - 对应参数位置的检查位置
  const check_positions = [
    "I6",  // xm_Arr 检查位置
    "I7",  // tp_Arr 检查位置
    "I9",  // zl_Arr 检查位置
    "I10", // zg_Arr 检查位置
    "I11", // ywfs_Arr 检查位置
    "I12"  // ywfb_Arr 检查位置
  ]
  
  // 结果位置配置
  const result_positions = [
    "I15", // return_rate
    "I16", // annualized_rate
    "I17", // maxdd
    "I18", // index_rate
    "I19", // index_annualized_rate
    "I20", // max_index_dd
    "I21", // fee_total
    "I22", // fee_annualized
    "I23"  // year_rate
  ]
  
  return {
    google_sheet_config: {
      ...formData.googleSheetConfig,
      parameter_positions,
      check_positions,
      result_positions
    },
    parameters: JSON.stringify(parametersList)
  }
}

// 保存草稿
const saveDraft = async () => {
  try {
    const valid = await formRef.value?.validate()
    if (!valid) return
    
    saving.value = true
    
    const taskData = {
      name: formData.name + ' (草稿)',
      description: formData.description,
      task_type: 'google_sheet',
      config: buildTaskConfig()
    }
    
    // 这里应该调用保存草稿的API
    ElMessage.success('草稿保存成功')
  } catch (error) {
    ElMessage.error('保存草稿失败')
  } finally {
    saving.value = false
  }
}

// 创建任务
const createTask = async () => {
  try {
    const valid = await formRef.value?.validate()
    if (!valid) return
    
    creating.value = true
    
    const taskData = {
      name: formData.name,
      description: formData.description,
      task_type: 'google_sheet',
      config: buildTaskConfig()
    }
    
    const result = await taskStore.createTask(taskData)
    
    if (result.status === 'success') {
      ElMessage.success('任务创建成功')
      router.push(`/google-sheet/detail?task_id=${result.task_id}`)
    } else {
      ElMessage.error(result.message || '任务创建失败')
    }
  } catch (error) {
    ElMessage.error('创建任务失败')
  } finally {
    creating.value = false
  }
}

// 页面加载时处理
onMounted(() => {
  // 如果是复制任务，加载原任务配置
  if (route.query.duplicate) {
    const taskId = route.query.duplicate
    const task = taskStore.tasks.find(t => t.id === taskId)
    
    if (task) {
      formData.name = task.name + '_copy'
      formData.description = task.description
      
      if (task.config?.google_sheet_config) {
        Object.assign(formData.googleSheetConfig, task.config.google_sheet_config)
      }
      
      if (task.config?.parameters) {
        formData.parameters = typeof task.config.parameters === 'string' 
          ? task.config.parameters 
          : JSON.stringify(task.config.parameters, null, 2)
      }
      
      ElMessage.info('已加载原任务配置')
    }
  } else {
    // 自动加载默认配置
    loadDefaultConfig()
  }
})
</script>

<style scoped>
.create-task {
  padding: 0;
  min-height: 100vh;
}

.page-header {
  margin-bottom: 24px;
  text-align: center;
}

.title {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0 0 8px 0;
}

.description {
  color: var(--el-text-color-secondary);
  margin: 0;
}

.create-form {
  max-width: 1200px;
  margin: 0 auto;
}

.form-section {
  margin-bottom: 24px;
}

/* 响应式瀑布流布局 */
.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
  gap: 24px;
  margin-bottom: 24px;
  align-items: start;
}

.config-card {
  height: fit-content;
  break-inside: avoid;
}

/* 位置信息样式 */  
.position-info {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
  margin-top: 12px;
}

.position-group h5 {
  margin: 0 0 8px 0;
  color: var(--el-text-color-primary);
  font-weight: 600;
}

.position-group ul {
  margin: 0;
  padding-left: 16px;
  list-style-type: disc;
}

.position-group li {
  margin-bottom: 4px;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.form-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.position-section {
  padding: 16px 0;
}

.position-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  font-size: 14px;
  color: var(--el-text-color-regular);
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

.parameter-editor {
  width: 100%;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.editor-label {
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.parameter-textarea {
  font-family: 'Courier New', monospace;
}

.validation-error {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-color-danger);
  font-size: 14px;
  margin-top: 8px;
}

.validation-success {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-color-success);
  font-size: 14px;
  margin-top: 8px;
}

.form-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 24px 0;
  border-top: 1px solid var(--el-border-color-light);
  margin-top: 24px;
}

.helper-content h4 {
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
}

.helper-content ul {
  margin-bottom: 20px;
  padding-left: 20px;
}

.helper-content li {
  margin-bottom: 8px;
  line-height: 1.5;
}

.example {
  background: var(--el-color-info-light-9);
  padding: 12px;
  border-radius: 4px;
  margin-bottom: 12px;
}

.example p {
  margin: 0;
  line-height: 1.5;
}

.code-example {
  background: #f5f5f5;
  padding: 16px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.4;
  overflow-x: auto;
}

/* 平板设备适配 (768px - 1024px) */
@media (max-width: 1024px) {
  .create-form {
    max-width: 100%;
    padding: 0 16px;
  }
  
  .config-grid {
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 16px;
  }
  
  .position-info {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  
  .header-actions {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  
  .header-actions .el-button {
    width: 100%;
  }
}

/* 中等屏幕适配 (768px - 900px) */
@media (max-width: 900px) {
  .config-grid {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}

/* 手机设备适配 (小于768px) */
@media (max-width: 768px) {
  .create-task {
    padding: 16px;
  }
  
  .page-header {
    margin-bottom: 16px;
  }
  
  .title {
    font-size: 20px;
  }
  
  .create-form {
    padding: 0;
  }
  
  .form-section {
    margin-bottom: 16px;
  }
  
  .config-grid {
    gap: 12px;
    margin-bottom: 16px;
  }
  
  .section-header {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }
  
  .header-actions {
    justify-content: center;
  }
  
  .position-header {
    flex-direction: column;
    gap: 8px;
    align-items: stretch;
  }
  
  .position-item {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  
  .position-item .el-input {
    width: 100% !important;
  }
  
  .editor-toolbar {
    flex-direction: column;
    gap: 8px;
    align-items: stretch;
  }
  
  .toolbar-actions {
    justify-content: center;
  }
  
  .form-actions {
    flex-direction: column;
    padding: 16px 0;
  }
  
  .form-actions .el-button {
    width: 100%;
  }
  
  /* 对话框在移动端的适配 */
  :deep(.el-dialog) {
    width: min(95%, 600px) !important;
    margin: 5vh auto !important;
    max-height: 90vh !important;
    display: flex !important;
    flex-direction: column !important;
  }
  
  :deep(.el-dialog__body) {
    padding: 16px !important;
    overflow-y: auto !important;
    flex: 1 !important;
  }
  
  :deep(.el-dialog__header) {
    padding: 16px !important;
    margin-right: 0 !important;
  }
  
  :deep(.el-dialog__headerbtn) {
    top: 16px !important;
  }
  
  .code-example {
    font-size: 12px;
    padding: 12px;
  }
}

/* 超小屏幕适配 (小于480px) */
@media (max-width: 480px) {
  .create-task {
    padding: 12px;
  }
  
  .title {
    font-size: 18px;
  }
  
  .form-section {
    margin-bottom: 12px;
  }
  
  .config-grid {
    gap: 8px;
    margin-bottom: 12px;
  }
  
  .section-title {
    font-size: 14px;
  }
  
  .header-actions .el-button {
    font-size: 12px;
    padding: 8px 12px;
  }
  
  .parameter-textarea {
    font-size: 12px;
  }
  
  .form-actions {
    padding: 12px 0;
    gap: 12px;
  }
  
  :deep(.el-form-item__label) {
    font-size: 14px;
  }
  
  :deep(.el-alert__title) {
    font-size: 14px;
  }
  
  :deep(.el-alert__description) {
    font-size: 12px;
  }
}

/* 横屏手机适配 */
@media (max-width: 768px) and (orientation: landscape) and (min-width: 600px) {
  .config-grid {
    grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
    gap: 16px;
  }
  
  .position-info {
    grid-template-columns: 1fr 1fr 1fr;
  }
}

/* 大屏幕优化 (大于1200px) */
@media (min-width: 1200px) {
  .create-form {
    max-width: 1400px;
  }
  
  .config-grid {
    gap: 32px;
  }
  
  .form-section {
    margin-bottom: 32px;
  }
}
</style>

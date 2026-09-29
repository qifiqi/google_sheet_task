<template>
  <!-- C4/C5/C7 共享编辑配置弹窗（对齐 static/js/common/business/config-edit.js openEditConfigModal
       + 各版本页 saveTaskConfig：产品代码 chips、多 sheets 行编辑、count_mode/date_range/日期、
       market、token_type file/json 切换校验；C3 不使用本弹窗） -->
  <el-dialog
    :model-value="visible"
    title="编辑任务配置"
    width="860px"
    :fullscreen="isMobile"
    :close-on-click-modal="false"
    @update:model-value="emit('update:visible', $event)"
  >
    <el-alert
      type="warning"
      :closable="false"
      title="注意：修改配置后，建议从头重新执行任务以确保数据一致性。如果从断点继续，请确保参数组合数量和顺序没有改变。"
      class="config-edit-dialog__alert"
    />

    <el-form label-width="170px">
      <el-form-item label="任务名称">
        <el-input v-model="form.name" placeholder="请输入任务名称" />
      </el-form-item>
      <el-form-item label="任务描述">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="请输入任务描述" />
      </el-form-item>

      <el-divider content-position="left">Google Sheet 配置</el-divider>

      <el-form-item label="股票/产品代码">
        <!-- 老版 chips 输入：输入后回车/点添加生成标签，对应 parameters[0] -->
        <el-select
          v-model="form.productCodes"
          multiple
          filterable
          allow-create
          default-first-option
          :reserve-keyword="false"
          placeholder="输入代码后回车添加，支持逗号/空格分隔批量粘贴，如：600000,600001"
          class="config-edit-dialog__codes"
          @change="handleProductCodesChange"
        >
          <el-option v-for="code in form.productCodes" :key="code" :value="code" :label="code" />
        </el-select>
      </el-form-item>
      <el-form-item label="参数组合说明">
        <span class="panel-note">产品代码将构成为 parameters[0]，与 Sheet 参数位组合生成参数组合。</span>
      </el-form-item>

      <el-form-item label="工作表配置">
        <div class="config-edit-dialog__sheets">
          <div
            v-for="(sheet, idx) in form.sheets"
            :key="idx"
            class="control-row control-row--stretch"
          >
            <el-input v-model="sheet.spreadsheet_id" placeholder="spreadsheet_id" />
            <el-input v-model="sheet.title" placeholder="title" />
            <el-input v-model="sheet.sheet_name" placeholder="sheet_name" />
            <el-button
              type="danger"
              plain
              :disabled="form.sheets.length <= 1"
              @click="form.sheets.splice(idx, 1)"
            >
              删除
            </el-button>
          </div>
          <div class="control-row">
            <el-button size="small" @click="addSheetRow">添加工作表</el-button>
            <el-button size="small" :disabled="form.sheets.length <= 1" @click="removeLastSheetRow">
              移除最后一行
            </el-button>
          </div>
        </div>
      </el-form-item>

      <el-collapse v-model="advancedOpen">
        <el-collapse-item title="更多参数" name="advanced">
          <el-row :gutter="12">
            <el-col :xs="24" :sm="8">
              <el-form-item label="统计方式 count_mode">
                <el-select v-model="form.countMode">
                  <el-option value="n_plus_1" label="n_plus_1" />
                  <el-option value="total" label="total" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="16">
              <el-form-item label="时间范围类型">
                <el-checkbox-group v-model="form.dateRangeModes" :disabled="form.countMode !== 'n_plus_1'">
                  <el-checkbox value="full">整年 full</el-checkbox>
                  <el-checkbox value="recent">近年 recent</el-checkbox>
                </el-checkbox-group>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="开始日期 start_date">
                <el-date-picker
                  v-model="form.startDate"
                  type="date"
                  value-format="YYYY-MM-DD"
                  placeholder="选择开始日期"
                  class="config-edit-dialog__date"
                />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="结束日期 end_date">
                <el-date-picker
                  v-model="form.endDate"
                  type="date"
                  value-format="YYYY-MM-DD"
                  placeholder="选择结束日期"
                  class="config-edit-dialog__date"
                />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-form-item label="市场类型 market_type">
                <el-input v-model="form.marketType" placeholder="如：cn" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-form-item label="代理地址 proxy_url">
                <el-input v-model="form.proxyUrl" placeholder="可选，HTTP/HTTPS 代理URL" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-form-item label="认证方式 token_type">
                <el-select v-model="form.tokenType">
                  <el-option value="file" label="文件 token_file" />
                  <el-option value="json" label="JSON token_json" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col v-if="form.tokenType === 'file'" :span="24">
              <el-form-item label="Token 文件路径">
                <el-input v-model="form.tokenFile" placeholder="如 data/token.json" />
              </el-form-item>
            </el-col>
            <el-col v-if="form.tokenType === 'json'" :span="24">
              <el-form-item label="Token JSON 字符串">
                <el-input v-model="form.tokenJson" type="textarea" :rows="3" placeholder="粘贴 JSON 字符串" />
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item label="完整参数结构">
                <el-input :model-value="parametersRaw" type="textarea" :rows="4" readonly />
                <div class="panel-note">
                  这里展示完整的 config.parameters JSON，仅供参考，真正提交时将以上方产品代码为准构造 parameters[0]。
                </div>
              </el-form-item>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { updateTaskConfig } from '@/api/task'
import { useResponsive } from '@/composables/useResponsive'

const props = defineProps({
  visible: { type: Boolean, default: false },
  // 任务对象（含 config，可能是对象或 JSON 字符串）
  task: { type: Object, default: null },
  // 版本标识：'c4' | 'c5' | 'c7'（三版编辑弹窗字段与保存 payload 一致，仅用于语义标注）
  version: { type: String, required: true }
})

const emit = defineEmits(['update:visible', 'saved'])

const { isMobile } = useResponsive()

const saving = ref(false)
const advancedOpen = ref([])
const form = reactive({
  name: '',
  description: '',
  productCodes: [],
  sheets: [],
  countMode: 'n_plus_1',
  dateRangeModes: ['full'],
  startDate: null,
  endDate: null,
  marketType: '',
  proxyUrl: '',
  tokenType: 'file',
  tokenFile: 'data/token.json',
  tokenJson: ''
})

function parseConfig(config) {
  if (typeof config === 'string') {
    try {
      return JSON.parse(config)
    } catch {
      return {}
    }
  }
  return config || {}
}

const parsedConfig = computed(() => parseConfig(props.task?.config))

const parametersRaw = computed(() => {
  const config = parsedConfig.value
  try {
    return config.parameters ? JSON.stringify(config.parameters, null, 2) : ''
  } catch {
    return ''
  }
})

function addSheetRow() {
  form.sheets.push({ spreadsheet_id: '', title: '', sheet_name: '' })
}

function removeLastSheetRow() {
  if (form.sheets.length > 1) {
    form.sheets.pop()
  }
}

// 打开时按任务配置回填（对齐 config-edit.js openEditConfigModal 的逐字段填充）
function fillForm() {
  const taskData = props.task
  if (!taskData) return
  const config = parsedConfig.value

  form.name = taskData.name || ''
  form.description = taskData.description || ''

  // 主参数：parameters[0] 渲染为 chips（去重、字符串化，同 renderEditProductCodeChips）
  const mainParams = Array.isArray(config.parameters?.[0]) ? config.parameters[0].slice() : []
  const unique = []
  const seen = new Set()
  mainParams.forEach((c) => {
    const val = String(c).trim()
    if (!val || seen.has(val)) return
    seen.add(val)
    unique.push(val)
  })
  form.productCodes = unique

  // sheets 多行：无配置时保留一行空行（同 renderEditSheetsRows）
  const sheets = Array.isArray(config.sheets) ? config.sheets : []
  form.sheets = (sheets.length > 0 ? sheets : [{}]).map((s) => ({
    spreadsheet_id: s?.spreadsheet_id || '',
    title: s?.title || '',
    sheet_name: s?.sheet_name || ''
  }))

  form.countMode = config.count_mode || 'n_plus_1'

  let drmList = []
  if (Array.isArray(config.date_range_mode)) {
    drmList = config.date_range_mode
  } else if (typeof config.date_range_mode === 'string' && config.date_range_mode) {
    drmList = [config.date_range_mode]
  }
  form.dateRangeModes = drmList.length ? drmList : ['full']

  form.startDate = config.start_date || null
  form.endDate = config.end_date || null
  form.marketType = config.market_type || ''
  form.tokenType = config.token_type || 'file'
  form.tokenFile = config.token_file || 'data/token.json'
  form.tokenJson = config.token_json || ''
  form.proxyUrl = config.proxy_url || ''
}

watch(() => props.visible, (visible) => {
  if (visible) {
    advancedOpen.value = []
    fillForm()
  }
})

// 批量粘贴拆分：allow-create 不按分隔符拆分，粘贴 "600000,600001" 会生成单个合并标签，
// 这里在 change 时按老版 chips 的 /[\s,，]+/ 规则拆开（程序赋值不触发 change，无递归）
function handleProductCodesChange(values) {
  const result = []
  const seen = new Set()
  values.forEach((raw) => {
    String(raw).split(/[\s,，]+/).forEach((part) => {
      const val = part.trim()
      if (val && !seen.has(val)) {
        seen.add(val)
        result.push(val)
      }
    })
  })
  form.productCodes = result
}

// 保存（对齐各版本页 saveTaskConfig 的校验与 payload 形状）
async function handleSave() {
  const name = form.name.trim()
  if (!name) {
    ElMessage.error('请输入任务名称')
    return
  }

  // 主参数：从代码列表收集 parameters[0]
  const params0 = []
  const seen = new Set()
  form.productCodes.forEach((c) => {
    const val = String(c).trim()
    if (val && !seen.has(val)) {
      seen.add(val)
      params0.push(val)
    }
  })
  if (!params0.length) {
    ElMessage.error('请至少添加一个产品代码（parameters[0]）')
    return
  }

  // sheets：收集非空行（全空行丢弃；title 有值才带上）
  const sheets = []
  form.sheets.forEach((sheet) => {
    const sid = (sheet.spreadsheet_id || '').trim()
    const sname = (sheet.sheet_name || '').trim()
    const title = (sheet.title || '').trim()
    if (sid || sname || title) {
      const item = {
        spreadsheet_id: sid || null,
        sheet_name: sname || null
      }
      if (title) item.title = title
      sheets.push(item)
    }
  })

  const countMode = form.countMode || 'n_plus_1'
  const dateRangeModeList = form.dateRangeModes.slice()
  if (dateRangeModeList.length === 0) {
    dateRangeModeList.push('full')
  }

  const tokenType = form.tokenType
  const tokenFile = form.tokenFile.trim()
  const tokenJson = form.tokenJson.trim()

  if (tokenType === 'file' && !tokenFile) {
    ElMessage.error('请输入 Token 文件路径')
    return
  }
  if (tokenType === 'json' && !tokenJson) {
    ElMessage.error('请输入 Token JSON 字符串')
    return
  }

  const config = {
    count_mode: countMode,
    date_range_mode: dateRangeModeList,
    start_date: form.startDate || null,
    end_date: form.endDate || null,
    market_type: form.marketType.trim() || null,
    parameters: [params0],
    sheets,
    proxy_url: form.proxyUrl.trim() || null,
    token_type: tokenType,
    token_file: tokenFile,
    token_json: tokenJson
  }

  saving.value = true
  try {
    await updateTaskConfig(props.task.id, {
      name,
      description: form.description.trim(),
      config
    })
    ElMessage.success('配置更新成功')
    emit('update:visible', false)
    emit('saved')
  } catch (e) {
    ElMessage.error(`配置更新失败: ${e?.message || '未知错误'}`)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.config-edit-dialog__alert {
  margin-bottom: 12px;
}

.config-edit-dialog__codes {
  width: 100%;
}

.config-edit-dialog__sheets {
  display: grid;
  gap: 8px;
  width: 100%;
}

.config-edit-dialog__date {
  width: 100%;
}
</style>

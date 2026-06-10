<template>
  <div class="backtest-multi-create-page">
    <PageToolbar eyebrow="多产品回测" title="创建多产品回测任务" />

    <el-card shadow="never" class="form-card">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="110px"
        label-position="top"
      >
        <!-- Excel 上传 -->
        <el-form-item label="Excel 文件" prop="file">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".xlsx,.xls"
            :on-change="handleFileChange"
            :on-exceed="handleExceed"
            :on-remove="handleRemove"
            drag
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽文件至此，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 .xlsx / .xls 格式</div>
            </template>
          </el-upload>
        </el-form-item>

        <!-- 市场选择 -->
        <el-form-item label="市场类型" prop="market_type">
          <el-radio-group v-model="form.market_type">
            <el-radio-button value="cn">A股</el-radio-button>
            <el-radio-button value="en">美股</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 股票搜索 -->
        <el-form-item label="关联股票" prop="stock_code">
          <el-autocomplete
            v-model="stockInput"
            :fetch-suggestions="handleStockQuery"
            :placeholder="stockLoading ? '搜索中...' : '输入股票代码或名称'"
            :disabled="stockLoading"
            value-key="code"
            clearable
            @select="handleStockSelect"
            style="width: 100%"
          >
            <template #default="{ item }">
              <span style="font-weight: 600">{{ item.code }}</span>
              <span style="color: var(--el-text-color-secondary); margin-left: 8px">{{ item.name }}</span>
            </template>
          </el-autocomplete>
        </el-form-item>

        <!-- 年份范围 -->
        <el-form-item label="回测年份范围" prop="year_range">
          <div class="year-range-row">
            <el-date-picker
              v-model="form.start_date"
              type="year"
              placeholder="开始年份"
              value-format="YYYY"
              style="flex: 1"
            />
            <span class="year-range-sep">至</span>
            <el-date-picker
              v-model="form.end_date"
              type="year"
              placeholder="结束年份"
              value-format="YYYY"
              style="flex: 1"
            />
          </div>
        </el-form-item>

        <!-- 任务备注 -->
        <el-form-item label="任务备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="可选填写任务备注" />
        </el-form-item>

        <!-- 操作按钮 -->
        <el-form-item>
          <div class="form-actions">
            <el-button @click="router.push('/backtest-multi/list')">取消</el-button>
            <el-button type="primary" :loading="submitting" @click="handleSubmit">
              提交创建
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, genFileId } from 'element-plus'
import { importExcel, searchStocks } from '@/api/backtestMulti'
import PageToolbar from '@/components/PageToolbar.vue'

const router = useRouter()
const formRef = ref(null)
const uploadRef = ref(null)

const submitting = ref(false)
const stockInput = ref('')
const stockLoading = ref(false)
const selectedStock = ref(null)
let stockTimer = null

const form = reactive({
  file: null,
  market_type: 'cn',
  stock_code: '',
  start_date: '',
  end_date: '',
  remark: '',
})

const rules = {
  file: [{ required: true, message: '请上传 Excel 文件', trigger: 'change' }],
  market_type: [{ required: true, message: '请选择市场类型', trigger: 'change' }],
}

function handleStockQuery(query, cb) {
  const q = (query || '').trim()
  if (!q) { cb([]); return }

  if (stockTimer) clearTimeout(stockTimer)
  stockTimer = setTimeout(async () => {
    stockLoading.value = true
    try {
      const params = { q, market: form.market_type }
      Object.keys(params).forEach(k => { if (!params[k]) delete params[k] })
      const res = await searchStocks(params)
      const data = Array.isArray(res) ? res : (res.data || res.results || [])
      cb(data.map(item => ({
        code: item.code || item.stock_code || '',
        name: item.name || item.stock_name || '',
        ...item,
      })))
    } catch {
      cb([])
    } finally {
      stockLoading.value = false
    }
  }, 300)
}

function handleStockSelect(item) {
  selectedStock.value = item
  form.stock_code = item.code
  stockInput.value = `${item.code} - ${item.name}`
}

function handleFileChange(file) {
  form.file = file.raw
  formRef.value?.clearValidate('file')
}

function handleExceed(files) {
  uploadRef.value?.clearFiles()
  const file = files[0]
  file.uid = genFileId()
  uploadRef.value?.handleStart(file)
  form.file = file
}

function handleRemove() {
  form.file = null
}

async function handleSubmit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    const fd = new FormData()
    fd.append('file', form.file)
    fd.append('market_type', form.market_type)
    if (form.stock_code) fd.append('stock_code', form.stock_code)
    if (form.start_date) fd.append('start_date', form.start_date)
    if (form.end_date) fd.append('end_date', form.end_date)
    if (form.remark) fd.append('remark', form.remark)

    await importExcel(fd)
    ElMessage.success('多产品回测任务创建成功，即将跳转')
    router.push('/backtest-multi/list')
  } catch (err) {
    ElMessage.error(err?.response?.data?.message || '创建失败，请重试')
  } finally {
    submitting.value = false
  }
}
</script>

<style lang="scss" scoped>
.backtest-multi-create-page {
  max-width: 720px;
}

.form-card {
  margin-top: 8px;
}

.year-range-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.year-range-sep {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  width: 100%;
  padding-top: 8px;
}
</style>

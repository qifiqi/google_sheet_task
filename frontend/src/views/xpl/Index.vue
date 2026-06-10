<template>
  <div class="xpl-index-page">
    <PageToolbar eyebrow="数据分析" title="夏普率计算">
      <template #actions>
        <el-button
          type="primary"
          plain
          :loading="exporting"
          :disabled="!resultRows.length"
          @click="handleExport"
        >
          <el-icon style="margin-right: 4px"><Download /></el-icon>导出结果
        </el-button>
      </template>
    </PageToolbar>

    <el-row :gutter="16">
      <!-- Input Panel -->
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="input-card">
          <template #header>数据输入</template>

          <el-form label-position="top">
            <el-form-item label="时间格式">
              <el-radio-group v-model="timeFormat" size="small">
                <el-radio-button value="daily">日频</el-radio-button>
                <el-radio-button value="weekly">周频</el-radio-button>
                <el-radio-button value="monthly">月频</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="无风险利率（年化 %）">
              <el-input-number
                v-model="riskFreeRate"
                :min="0"
                :max="100"
                :step="0.1"
                :precision="2"
                style="width: 160px"
              />
            </el-form-item>

            <el-form-item label="粘贴数据（每行一个收益率，或 CSV 格式）">
              <el-input
                v-model="rawData"
                type="textarea"
                :rows="14"
                placeholder="示例：&#10;0.01&#10;-0.005&#10;0.02&#10;0.008&#10;&#10;或 CSV：&#10;date,return&#10;2024-01-01,0.01&#10;2024-01-02,-0.005"
              />
            </el-form-item>

            <el-form-item>
              <div class="form-actions">
                <el-button @click="rawData = ''">清空</el-button>
                <el-button type="primary" :loading="analyzing" @click="handleAnalyze">
                  开始分析
                </el-button>
              </div>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- Results Panel -->
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="result-card">
          <template #header>
            <div class="card-header">
              <span>分析结果</span>
              <el-tag v-if="resultRows.length" type="success" size="small">
                {{ resultRows.length }} 条数据
              </el-tag>
            </div>
          </template>

          <template v-if="summaryStats.length">
            <StatCardGrid
              :cards="summaryStats"
              :data="summaryData"
              :columns="{ xs: 12, sm: 8, md: 8 }"
              class="mb-4"
            />
          </template>

          <el-table
            v-if="resultRows.length"
            :data="resultRows"
            stripe
            border
            style="width: 100%"
            max-height="400"
          >
            <el-table-column
              v-for="col in resultColumns"
              :key="col.prop"
              :prop="col.prop"
              :label="col.label"
              :min-width="col.minWidth"
              show-overflow-tooltip
            />
          </el-table>

          <EmptyState v-if="!analyzing && !resultRows.length" description="请输入数据并点击分析" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { analyzeXplV1, exportXplResult } from '@/api/xpl'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import EmptyState from '@/components/EmptyState.vue'

const rawData = ref('')
const timeFormat = ref('daily')
const riskFreeRate = ref(2.0)
const analyzing = ref(false)
const exporting = ref(false)
const analysisResult = ref(null)

const summaryData = computed(() => analysisResult.value?.summary || {})

const summaryStats = computed(() => {
  const s = summaryData.value
  if (!s || !Object.keys(s).length) return []
  return Object.keys(s).map(key => ({ key, label: key }))
})

const resultRows = computed(() => {
  if (!analysisResult.value) return []
  return analysisResult.value.rows || analysisResult.value.data || analysisResult.value.details || []
})

const resultColumns = computed(() => {
  const rows = resultRows.value
  if (!rows.length) return []
  return Object.keys(rows[0]).map(key => ({
    prop: key,
    label: key,
    minWidth: 100,
  }))
})

async function handleAnalyze() {
  if (!rawData.value.trim()) {
    ElMessage.warning('请先粘贴数据')
    return
  }

  analyzing.value = true
  try {
    const res = await analyzeXplV1({
      data: rawData.value,
      time_format: timeFormat.value,
      risk_free_rate: riskFreeRate.value / 100,
    })
    analysisResult.value = res.data || res
    ElMessage.success('分析完成')
  } catch (err) {
    ElMessage.error(err?.response?.data?.message || '分析失败，请检查数据格式')
  } finally {
    analyzing.value = false
  }
}

async function handleExport() {
  if (!analysisResult.value) return
  exporting.value = true
  try {
    const res = await exportXplResult({
      data: rawData.value,
      time_format: timeFormat.value,
      risk_free_rate: riskFreeRate.value / 100,
    })
    const blob = new Blob([res], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `xpl_analysis_${Date.now()}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style lang="scss" scoped>
.input-card,
.result-card {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  width: 100%;
}
</style>

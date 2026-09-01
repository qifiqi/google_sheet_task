<template>
  <div class="app-page backtest-multi-result-page">
    <PageToolbar
      eyebrow="Multi-Product Result"
      title="多产品回测结果"
      description="查看当前多产品回测任务的详细结果数据。"
    >
      <template #actions>
        <el-button @click="loadResult">刷新</el-button>
        <el-button class="page-back-button" @click="$router.push(`/backtest-multi/${taskId}`)">返回详情</el-button>
      </template>
    </PageToolbar>

    <div v-loading="loading">
      <el-card v-if="result" shadow="never" class="page-section">
        <div class="section-heading">
          <div>
            <h3 class="section-title section-title--muted">结果概览</h3>
            <div class="panel-note">结果 ID: {{ result.id || taskId }}</div>
          </div>
          <div class="section-actions">
            <el-button size="small" @click="copyRawJson">复制 JSON</el-button>
          </div>
        </div>

        <el-descriptions :column="2" border size="small" class="backtest-multi-result-page__desc">
          <el-descriptions-item label="状态">
            <el-tag :type="result.success ? 'success' : 'danger'" size="small">
              {{ result.success ? '成功' : '失败' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ result.timestamp || '-' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card v-if="result" shadow="never" class="page-section">
        <div class="section-heading">
          <h3 class="section-title section-title--muted">参数信息</h3>
        </div>
        <CodeBlock :code="JSON.stringify(result.parameters || {}, null, 2)" language="json" />
      </el-card>

      <el-card v-if="result" shadow="never" class="page-section">
        <div class="section-heading">
          <h3 class="section-title section-title--muted">执行结果</h3>
        </div>
        <CodeBlock :code="JSON.stringify(result.result || {}, null, 2)" language="json" />
      </el-card>

      <el-card v-if="result && result.error_message" shadow="never" class="page-section">
        <div class="section-heading">
          <h3 class="section-title section-title--muted">错误信息</h3>
        </div>
        <pre class="backtest-multi-result-page__error-block">{{ result.error_message }}</pre>
      </el-card>

      <el-empty v-if="!loading && !result" description="暂无回测结果" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getTaskResult } from '@/api/backtestMulti'
import PageToolbar from '@/components/PageToolbar.vue'
import CodeBlock from '@/components/CodeBlock.vue'

const route = useRoute()
const taskId = route.params.id
const loading = ref(false)
const result = ref(null)

async function loadResult() {
  loading.value = true
  try {
    const res = await getTaskResult(taskId)
    result.value = res.result || res
  } catch {
    ElMessage.error('加载回测结果失败')
  } finally {
    loading.value = false
  }
}

async function copyRawJson() {
  try {
    await navigator.clipboard.writeText(JSON.stringify(result.value, null, 2))
    ElMessage.success('复制成功')
  } catch {
    ElMessage.error('复制失败')
  }
}

onMounted(loadResult)
</script>

<style scoped>
.backtest-multi-result-page__desc {
  margin-bottom: 12px;
}

.backtest-multi-result-page__error-block {
  max-height: 250px;
  margin: 0;
  overflow: auto;
  padding: 12px;
  border-radius: 12px;
  background: #fef2f2;
  color: #dc2626;
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.6;
}
</style>

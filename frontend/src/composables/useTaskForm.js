import { ref, reactive, computed } from 'vue'
import { createTask, batchCreateTasks } from '@/api/task'
import { getTemplates } from '@/api/template'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

export function useTaskForm(version = 'c3') {
  const router = useRouter()
  const loading = ref(false)
  const submitting = ref(false)

  const form = reactive({
    task_name: '',
    task_description: '',
    template_id: '',
    spreadsheet_id: '',
    spreadsheet_title: '',
    sheet_name: '',
    google_sheet_id: '',
    token_type: 'file',
    token_file: 'data/token.json',
    token_json: '',
    proxy_url: '',
    parameters: [{ id: 1, values: '' }],
  })

  // C31 batch mode
  const isBatch = computed(() => version === 'c31')

  const parameterCount = computed(() => form.parameters.length)

  const totalCombinations = computed(() => {
    return form.parameters.reduce((acc, param) => {
      try {
        const arr = JSON.parse(param.values)
        if (Array.isArray(arr) && arr.length > 0) {
          return acc * arr.length
        }
      } catch {}
      return acc
    }, 1)
  })

  function addParameter() {
    const nextId = form.parameters.length > 0
      ? Math.max(...form.parameters.map(p => p.id)) + 1
      : 1
    form.parameters.push({ id: nextId, values: '' })
  }

  function removeParameter(index) {
    if (form.parameters.length <= 1) return
    form.parameters.splice(index, 1)
  }

  function clearParameters() {
    form.parameters = [{ id: 1, values: '' }]
  }

  function buildPayload() {
    const config = {
      spreadsheet_id: form.spreadsheet_id,
      spreadsheet_title: form.spreadsheet_title,
      sheet_name: form.sheet_name,
      google_sheet_id: form.google_sheet_id,
      token_type: form.token_type,
      proxy_url: form.proxy_url || undefined,
    }

    if (form.token_type === 'file') {
      config.token_file = form.token_file
    } else {
      config.token_json = form.token_json
    }

    const parameters = form.parameters
      .filter(p => p.values.trim())
      .map(p => {
        try { return JSON.parse(p.values) } catch { return [] }
      })

    const payload = {
      task_type: version === 'c31' ? 'google_sheet' : `google_sheet`,
      task_name: form.task_name || undefined,
      task_description: form.task_description || undefined,
      config: {
        ...config,
        version,
        parameters,
      },
    }

    return payload
  }

  async function submit() {
    submitting.value = true
    try {
      const payload = buildPayload()

      if (isBatch.value) {
        await batchCreateTasks(payload)
        ElMessage.success('批量任务已创建')
      } else {
        await createTask(payload)
        ElMessage.success('任务已创建')
      }

      router.push('/task/list')
    } catch (err) {
      ElMessage.error(err?.response?.data?.error || err?.message || '创建失败')
    } finally {
      submitting.value = false
    }
  }

  async function loadTemplate(templateId) {
    if (!templateId) return
    loading.value = true
    try {
      const { getTemplate } = await import('@/api/template')
      const res = await getTemplate(templateId)
      const tmpl = res.data || res
      if (tmpl.config) {
        const c = tmpl.config
        form.spreadsheet_id = c.spreadsheet_id || ''
        form.spreadsheet_title = c.spreadsheet_title || ''
        form.sheet_name = c.sheet_name || ''
        form.google_sheet_id = c.google_sheet_id || ''
        form.token_type = c.token_type || 'file'
        form.token_file = c.token_file || 'data/token.json'
        form.token_json = c.token_json || ''
        form.proxy_url = c.proxy_url || ''
        if (Array.isArray(c.parameters)) {
          form.parameters = c.parameters.map((p, i) => ({
            id: i + 1,
            values: typeof p === 'string' ? p : JSON.stringify(p),
          }))
        }
      }
      ElMessage.success('模板已加载')
    } catch {
      ElMessage.error('加载模板失败')
    } finally {
      loading.value = false
    }
  }

  async function saveAsTemplate() {
    const name = prompt('请输入模板名称：')
    if (!name) return
    try {
      const { createTemplate } = await import('@/api/template')
      await createTemplate({
        name,
        task_type: 'google_sheet',
        config: buildPayload().config,
      })
      ElMessage.success('模板已保存')
    } catch {
      ElMessage.error('保存模板失败')
    }
  }

  return {
    form,
    loading,
    submitting,
    isBatch,
    parameterCount,
    totalCombinations,
    addParameter,
    removeParameter,
    clearParameters,
    submit,
    loadTemplate,
    saveAsTemplate,
  }
}

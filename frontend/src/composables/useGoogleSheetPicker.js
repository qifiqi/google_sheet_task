import { ref, onMounted } from 'vue'
import { getGoogleSheets } from '@/api/googleSheet'
import { ElMessage } from 'element-plus'

export function useGoogleSheetPicker() {
  const sheets = ref([])
  const loading = ref(false)

  async function loadSheets() {
    loading.value = true
    try {
      const res = await getGoogleSheets()
      sheets.value = Array.isArray(res) ? res : (res.data || [])
    } catch {
      sheets.value = []
      ElMessage.error('加载 Google Sheet 列表失败')
    } finally {
      loading.value = false
    }
  }

  function findSheet(spreadsheetId) {
    return sheets.value.find((s) => s.spreadsheet_id === spreadsheetId)
  }

  onMounted(() => {
    loadSheets()
  })

  return {
    sheets,
    loading,
    loadSheets,
    findSheet,
  }
}

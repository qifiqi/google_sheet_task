import type { GoogleSheetSelection } from '../types/google-sheet'

export function createEmptySheet(): GoogleSheetSelection {
  return { spreadsheetId: '', title: '', sheetName: '' }
}

export function createParameterInputs() {
  return Array.from({ length: 6 }, () => '')
}

export function parseParameterInput(input: string, allowMatrix = false): unknown[] {
  const trimmed = input.trim()
  if (!trimmed) return []
  let value: unknown
  try {
    value = JSON.parse(trimmed)
  } catch {
    throw new Error('请输入有效的 JSON 数组')
  }
  if (!Array.isArray(value)) throw new Error('参数必须是 JSON 数组')
  if (allowMatrix && value.some((item) => Array.isArray(item) && item.length === 0)) {
    throw new Error('二维参数中的每一项不能是空数组')
  }
  if (!allowMatrix && value.some(Array.isArray)) throw new Error('C3 参数只支持一维数组')
  return value
}

export function parseParameterInputs(inputs: readonly string[], allowMatrix = false) {
  return inputs.map((input, index) => {
    try {
      return parseParameterInput(input, allowMatrix)
    } catch (error) {
      const message = error instanceof Error ? error.message : '参数格式错误'
      throw new Error(`参数 ${index + 1}：${message}`)
    }
  }).filter((item) => item.length > 0)
}

export function c31CombinationCount(parameterGroups: readonly unknown[][]) {
  return parameterGroups.reduce((total, group) => {
    if (group.length === 0) return total
    const count = Array.isArray(group[0]) ? group.length : 1
    return total * count
  }, 1)
}

export function parseC31SheetTitle(title: string) {
  const match = title.trim().match(/-(\d+)y-(\d+)\]$/)
  if (!match) return null
  return { year: `${match[1]}y`, order: Number(match[2]) }
}

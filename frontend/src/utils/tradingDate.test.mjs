import assert from 'node:assert/strict'
import test from 'node:test'

import { defaultDateRange, formatDate, previousWeekday } from './tradingDate.js'
import '../../../static/js/trading-date.js'

test('周一默认回退到上周五', () => {
  const monday = new Date(2024, 0, 8)

  assert.equal(formatDate(previousWeekday(monday)), '2024-01-05')
  assert.equal(globalThis.TradingDate.formatDate(globalThis.TradingDate.previousWeekday(monday)), '2024-01-05')
})

test('周末默认回退到上周五', () => {
  assert.equal(formatDate(previousWeekday(new Date(2024, 0, 7))), '2024-01-05')
  assert.equal(formatDate(previousWeekday(new Date(2024, 0, 6))), '2024-01-05')
})

test('默认区间的开始与结束日期都落在工作日', () => {
  const range = defaultDateRange(5, new Date(2024, 0, 8))

  assert.equal(formatDate(range.end), '2024-01-05')
  assert.equal(formatDate(range.start), '2019-01-04')
})

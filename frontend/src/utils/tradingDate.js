function cloneLocalDate(value = new Date()) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate())
}

export function previousWeekday(referenceDate = new Date()) {
  const date = cloneLocalDate(referenceDate)
  date.setDate(date.getDate() - 1)
  while (date.getDay() === 0 || date.getDay() === 6) {
    date.setDate(date.getDate() - 1)
  }
  return date
}

export function formatDate(date) {
  const localDate = cloneLocalDate(date)
  const month = String(localDate.getMonth() + 1).padStart(2, '0')
  const day = String(localDate.getDate()).padStart(2, '0')
  return `${localDate.getFullYear()}-${month}-${day}`
}

export function defaultDateRange(years, referenceDate = new Date()) {
  const end = previousWeekday(referenceDate)
  const start = cloneLocalDate(end)
  start.setFullYear(start.getFullYear() - years)
  while (start.getDay() === 0 || start.getDay() === 6) {
    start.setDate(start.getDate() - 1)
  }
  return { start, end }
}

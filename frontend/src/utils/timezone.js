// offsetminutes(예: 540) → "UTC+09:00"
export function fmtOffset(min) {
  const m = Number(min) || 0
  const sign = m < 0 ? '-' : '+'
  const abs = Math.abs(m)
  return `UTC${sign}${String(Math.floor(abs / 60)).padStart(2, '0')}:${String(abs % 60).padStart(2, '0')}`
}

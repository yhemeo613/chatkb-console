import dayjs from 'dayjs'

export function fmtTime(ts) {
  if (!ts) return '—'
  return dayjs(ts * (ts > 1e12 ? 1 : 1000)).format('YYYY-MM-DD HH:mm')
}

export function fmtSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = bytes
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}

export function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** 把查询词在文本中高亮（先转义再包 <mark>，避免 XSS） */
export function highlight(text, query) {
  const esc = escapeHtml(text)
  const terms = String(query || '').trim().split(/\s+/).filter((t) => t.length > 1)
  if (!terms.length) return esc
  const re = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
  return esc.replace(re, '<mark>$1</mark>')
}

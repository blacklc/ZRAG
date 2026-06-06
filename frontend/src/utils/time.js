/**
 * 相对时间格式化工具
 *
 * 将 ISO 时间字符串格式化为人类可读的相对时间描述。
 * 复用规则:
 *   - 1 分钟内 → "刚刚"
 *   - 1 小时内 → "N 分钟前"
 *   - 24 小时内 → "N 小时前"
 *   - 7 天内   → "N 天前"
 *   - 超过 7 天 → "yyyy-MM-dd"
 *   - 空值/非法值 → 空串
 *
 * 此模块由 ChatSidebar 和 SourcesView 共用,
 * 避免两处维护同样的阈值常量与格式化逻辑。
 */

/** 时间区间阈值 (秒) */
const THRESHOLDS = Object.freeze({
  MINUTE: 60,
  HOUR: 3600,
  DAY: 86400,
  WEEK: 604800,
})

/**
 * 将秒差转换为人类可读的字符串表示
 *
 * @param {number} diffSec - 与当前时间的差值 (秒)
 * @param {Date} date - 原始 Date 对象
 * @returns {string} 相对时间字符串
 */
function formatRelativeDiff(diffSec, date) {
  const { MINUTE, HOUR, DAY, WEEK } = THRESHOLDS
  if (diffSec < MINUTE) return '刚刚'
  if (diffSec < HOUR) return `${Math.floor(diffSec / MINUTE)} 分钟前`
  if (diffSec < DAY) return `${Math.floor(diffSec / HOUR)} 小时前`
  if (diffSec < WEEK) return `${Math.floor(diffSec / DAY)} 天前`
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * 将 ISO 时间格式化为相对时间字符串
 *
 * @param {string} isoTime - ISO 格式时间字符串
 * @returns {string} 相对时间字符串; 空值或非法值时返回空串
 */
export function formatRelativeTime(isoTime) {
  if (!isoTime) return ''
  // SQLite datetime('now') 返回 UTC 但无时区标识，追加 Z 让 JS 按 UTC 解析
  const date = new Date(isoTime.replace(' ', 'T') + 'Z')
  if (Number.isNaN(date.getTime())) return isoTime
  const diffSec = Math.floor((Date.now() - date.getTime()) / 1000)
  return formatRelativeDiff(Math.max(0, diffSec), date)
}

/**
 * 摄入任务状态领域常量
 *
 * 集中管理所有与任务状态相关的字符串映射、判断逻辑与工具函数。
 * 业务组件通过 import { getStatusText, isIndeterminateStatus, ... } from '@/constants/ingest'
 * 使用本模块提供的功能，避免在各组件中重复硬编码状态判断逻辑。
 */

/**
 * 后端状态值 -> 前端显示文本映射
 *
 * @type {Object<string, string>}
 */
export const STATUS_TEXT = {
  pending: '正在准备中...',
  waiting: '等待导出笔记...',
  processing: '正在处理中...',
  done: '处理完成',
  cancelled: '已取消',
  failed: '处理失败',
}

/**
 * 终态集合
 *
 * 达终态后停止轮询，不再更新状态。
 *
 * @type {Set<string>}
 */
export const TERMINAL_STATUSES = new Set(['done', 'cancelled', 'failed'])

/**
 * 不确定进度状态集合
 *
 * 当任务处于这些状态时，进度条应显示为 indeterminate 动画。
 * 注意 processing 状态也可能属于此集合，取决于 total 是否已知。
 *
 * @type {Set<string>}
 */
export const INDETERMINATE_STATUSES = new Set(['pending', 'waiting'])

/**
 * 获取状态对应的显示文本
 *
 * 对 processing 和 done 提供特殊格式化:
 *   - processing 且 total > 0 时显示 "正在处理（processed/total）"
 *   - done 且 total > 0 时显示 "处理完成，共处理 total 篇"
 *
 * @param {string} status - 后端返回的状态值
 * @param {number} [total=0] - 文档总数
 * @param {number} [processed=0] - 已处理文档数
 * @returns {string} 前端显示的文本
 */
export function getStatusText(status, total = 0, processed = 0) {
  switch (status) {
    case 'processing':
      return total > 0
        ? `正在处理（${processed}/${total}）`
        : STATUS_TEXT.processing
    case 'done':
      return total > 0
        ? `处理完成，共处理 ${total} 篇`
        : STATUS_TEXT.done
    default:
      return STATUS_TEXT[status] || STATUS_TEXT.processing
  }
}

/**
 * 判断是否应显示为不确定进度条
 *
 * @param {string} status - 后端返回的状态值
 * @param {number} [total=0] - 文档总数
 * @returns {boolean} true 表示需要显示 indeterminate 进度条
 */
export function isIndeterminateStatus(status, total = 0) {
  return INDETERMINATE_STATUSES.has(status) || (status === 'processing' && total === 0)
}

/**
 * 判断是否应显示为确定进度条
 *
 * @param {string} status - 后端返回的状态值
 * @param {number} [total=0] - 文档总数
 * @returns {boolean} true 表示需要显示 determinate 进度条
 */
export function isDeterminateStatus(status, total = 0) {
  return status === 'processing' && total > 0
}

/**
 * 判断是否为终态
 *
 * @param {string} status - 后端返回的状态值
 * @returns {boolean} true 表示任务已结束
 */
export function isTerminalStatus(status) {
  return TERMINAL_STATUSES.has(status)
}

/**
 * 计算进度比例
 *
 * @param {number} processed - 已处理文档数
 * @param {number} total - 文档总数
 * @returns {number} 0-1 之间的进度比例，total 为 0 时返回 0
 */
export function progressRatio(processed, total) {
  return total > 0 ? processed / total : 0
}

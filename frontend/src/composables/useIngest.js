/**
 * 摄入业务逻辑 composable
 *
 * 封装摄入任务的完整生命周期:
 *   - 创建摄入任务 (异步，返回 task_id)
 *   - 轮询任务状态 (2s 间隔)
 *   - 取消任务
 *   - 跨页面恢复 (sessionStorage)
 *
 * 可用数据源列表逻辑已拆分至 useAvailableSources.js，状态显示文本与进度判断
 * 已抽取至 constants/ingest.js，以保持 composable 职责单一。
 */

import { ref, computed } from 'vue'
import {
  ingestDocuments,
  getTaskStatus,
  cancelIngestTask,
} from '../api/endpoints.js'
import {
  getStatusText,
  isIndeterminateStatus,
  isDeterminateStatus,
  isTerminalStatus,
  progressRatio as calcProgressRatio,
} from '../constants/ingest.js'

const STORAGE_KEY = 'activeIngestTask'

/**
 * 摄入任务生命周期管理 composable
 *
 * 提供摄入任务的创建、状态轮询、取消以及跨页面恢复等能力。
 * 通过 constants/ingest.js 中的工具函数处理状态判断与显示文本。
 *
 * @returns {{
 *   taskId: import('vue').Ref<string|null>,
 *   taskStatus: import('vue').Ref<string|null>,
 *   total: import('vue').Ref<number>,
 *   processed: import('vue').Ref<number>,
 *   ingesting: import('vue').Ref<boolean>,
 *   cancelLoading: import('vue').Ref<boolean>,
 *   statusText: import('vue').ComputedRef<string>,
 *   isIndeterminate: import('vue').ComputedRef<boolean>,
 *   isDeterminate: import('vue').ComputedRef<boolean>,
 *   progressRatio: import('vue').ComputedRef<number>,
 *   startIngest: (sourceType: string, full: boolean) => Promise<void>,
 *   cancelTask: () => Promise<void>,
 *   restoreActiveTask: () => void,
 *   startPolling: (tid?: string) => void,
 *   stopPolling: () => void,
 *   pollNow: (id: string) => Promise<void>,
 *   dispose: () => void,
 * }}
 */
export function useIngest() {
  /** 当前任务 ID */
  const taskId = ref(null)
  /** 当前任务状态值（pending / waiting / processing / done / cancelled / failed） */
  const taskStatus = ref(null)
  /** 待处理文档总数 */
  const total = ref(0)
  /** 已处理文档数 */
  const processed = ref(0)
  /** 是否正在执行摄入 */
  const ingesting = ref(false)
  /** 取消按钮加载状态 */
  const cancelLoading = ref(false)

  let pollTimer = null

  /**
   * 状态显示文本
   *
   * 基于 taskStatus、total 和 processed 动态计算。
   *
   * @type {import('vue').ComputedRef<string>}
   */
  const statusText = computed(() => getStatusText(taskStatus.value, total.value, processed.value))

  /**
   * 是否应显示不确定进度条
   *
   * @type {import('vue').ComputedRef<boolean>}
   */
  const isIndeterminate = computed(() => isIndeterminateStatus(taskStatus.value, total.value))

  /**
   * 是否应显示确定进度条
   *
   * @type {import('vue').ComputedRef<boolean>}
   */
  const isDeterminate = computed(() => isDeterminateStatus(taskStatus.value, total.value))

  /**
   * 进度比例（0-1）
   *
   * @type {import('vue').ComputedRef<number>}
   */
  const progressRatio = computed(() => calcProgressRatio(processed.value, total.value))

  /**
   * 是否已达终态
   *
   * 内部用于决定是否停止轮询。
   *
   * @type {import('vue').ComputedRef<boolean>}
   */
  const isTerminal = computed(() => isTerminalStatus(taskStatus.value))

  /**
   * 发起摄入
   *
   * @param {string} sourceType - 数据源类型
   * @param {boolean} full - 是否全量摄入
   * @returns {Promise<void>}
   */
  async function startIngest(sourceType, full) {
    if (ingesting.value) return
    ingesting.value = true
    taskStatus.value = 'pending'
    try {
      const result = await ingestDocuments({ source_type: sourceType, full })
      taskId.value = result.task_id
      sessionStorage.setItem(STORAGE_KEY, result.task_id)
      startPolling()
    } catch (e) {
      ingesting.value = false
      throw e
    }
  }

  /**
   * 立即轮询一次任务状态
   *
   * @param {string} id - 任务 ID
   */
  async function pollNow(id) {
    try {
      const data = await getTaskStatus(id)
      taskStatus.value = data.status
      total.value = data.total
      processed.value = data.processed
      if (isTerminalStatus(data.status)) {
        ingesting.value = false
        stopPolling()
        sessionStorage.removeItem(STORAGE_KEY)
      }
    } catch (e) {
      // 轮询失败不停止，持续重试
    }
  }

  /**
   * 开始轮询任务状态
   *
   * @param {string} [tid] - 任务 ID，不传则使用 taskId.value
   */
  function startPolling(tid) {
    stopPolling()
    const id = tid || taskId.value
    if (!id) return
    pollNow(id)  // 不 await，立即触发一次，不阻塞后续定时器启动
    pollTimer = setInterval(() => pollNow(id), 2000)
  }

  /**
   * 停止轮询
   */
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  /**
   * 取消当前任务
   *
   * @returns {Promise<void>}
   */
  async function cancelTask() {
    if (!taskId.value || cancelLoading.value) return
    cancelLoading.value = true
    try {
      await cancelIngestTask(taskId.value)
    } catch (e) {
      throw e
    } finally {
      cancelLoading.value = false
    }
  }

  /**
   * 恢复 sessionStorage 中存储的活跃任务
   */
  function restoreActiveTask() {
    const saved = sessionStorage.getItem(STORAGE_KEY)
    if (saved) {
      taskId.value = saved
      ingesting.value = true
      startPolling(saved)
    }
  }

  /**
   * 清理资源（组件卸载时调用）
   */
  function dispose() {
    stopPolling()
  }

  return {
    taskId,
    taskStatus,
    total,
    processed,
    ingesting,
    cancelLoading,
    statusText,
    isIndeterminate,
    isDeterminate,
    progressRatio,
    startIngest,
    cancelTask,
    restoreActiveTask,
    startPolling,
    stopPolling,
    pollNow,
    dispose,
  }
}

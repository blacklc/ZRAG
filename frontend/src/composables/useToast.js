/**
 * 全局 Toast 通知 composable
 *
 * 维护一个全局共享的 toasts 响应式数组,任何组件通过 useToast()
 * 都可以调用 success/error/info 触发通知,或 dismiss 手动关闭.
 * 单条 Toast 的自动消失由 show() 内部通过 setTimeout 调度.
 */

import { ref } from 'vue'

// 模块级共享状态:toasts 数组与自增 id
const toasts = ref([])
let nextId = 0

export function useToast() {
  /**
   * 推送一条 Toast 到全局队列.
   *
   * @param {string} type - 通知类型,支持 'success' | 'error' | 'info'
   * @param {string} message - 通知正文内容
   * @param {number} [duration=3000] - 自动消失的毫秒数,传 0 则不自动消失
   * @returns {number} 新增 Toast 的 id,可用于 dismiss
   */
  function show(type, message, duration = 3000) {
    const id = ++nextId
    toasts.value.push({ id, type, message })
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration)
    }
    return id
  }

  /**
   * 关闭指定 id 的 Toast(从队列中移除).
   *
   * @param {number} id - Toast id
   * @returns {void}
   */
  function dismiss(id) {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx >= 0) toasts.value.splice(idx, 1)
  }

  return {
    toasts,
    success: (msg, dur) => show('success', msg, dur),
    error: (msg, dur = 5000) => show('error', msg, dur),
    info: (msg, dur) => show('info', msg, dur),
    dismiss,
  }
}

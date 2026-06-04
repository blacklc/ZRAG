/**
 * useToast composable 测试
 *
 * 验证全局 Toast 通知队列的增删操作和模块级共享状态。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useToast } from '../../composables/useToast'

describe('useToast', () => {
  /**
   * 每个测试前重置模块级共享的 toasts 数组,
   * 避免测试之间相互影响。
   */
  beforeEach(() => {
    const { toasts } = useToast()
    toasts.value = []
  })

  it('应返回 toasts, dismiss, success, error, info 方法', () => {
    const toast = useToast()
    expect(toast).toHaveProperty('toasts')
    expect(toast).toHaveProperty('dismiss')
    expect(toast).toHaveProperty('success')
    expect(toast).toHaveProperty('error')
    expect(toast).toHaveProperty('info')
  })

  it('success — 调用 success(\'OK\') 后 toasts.value 新增一条 type=success, message=OK', () => {
    const { toasts, success } = useToast()
    success('OK')
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0]).toMatchObject({ type: 'success', message: 'OK' })
  })

  it('error — 调用 error(\'Err\') 后 toasts.value 新增一条 type=error, message=Err', () => {
    const { toasts, error } = useToast()
    error('Err')
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0]).toMatchObject({ type: 'error', message: 'Err' })
  })

  it('info — 调用 info(\'Info\') 后 toasts.value 新增一条 type=info, message=Info', () => {
    const { toasts, info } = useToast()
    info('Info')
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0]).toMatchObject({ type: 'info', message: 'Info' })
  })

  it('多 toast — 多次调用后 toasts.value 长度正确', () => {
    const { toasts, success, error, info } = useToast()
    success('A')
    error('B')
    info('C')
    success('D')
    expect(toasts.value).toHaveLength(4)
    expect(toasts.value.map((t) => t.message)).toEqual(['A', 'B', 'C', 'D'])
  })

  it('dismiss — 手动关闭指定 id 后该 toast 被移除', () => {
    const { toasts, success, error, info, dismiss } = useToast()
    info('Keep')
    const id = success('Remove me')
    error('Also Keep')
    expect(toasts.value).toHaveLength(3)
    dismiss(id)
    expect(toasts.value).toHaveLength(2)
    expect(toasts.value.find((t) => t.id === id)).toBeUndefined()
  })

  it('自动消失 — success 调用后 setTimeout 被触发', () => {
    vi.useFakeTimers()
    const spy = vi.spyOn(globalThis, 'setTimeout')
    const { success } = useToast()
    success('Auto dismiss')
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith(expect.any(Function), 3000)
    spy.mockRestore()
    vi.useRealTimers()
  })

  it('共享状态 — 多次调用 useToast() 共享同一个 toasts ref', () => {
    const a = useToast()
    const b = useToast()
    expect(a.toasts).toBe(b.toasts)
    a.success('hello')
    expect(b.toasts.value).toHaveLength(1)
    expect(b.toasts.value[0].message).toBe('hello')
  })
})

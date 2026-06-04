/**
 * ToastContainer.vue 组件测试
 *
 * 验证 Toast 容器组件的渲染逻辑:
 * - 初始状态无 toast
 * - success/error/info 三种类型的样式
 * - 手动关闭按钮
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import ToastContainer from '../../components/ToastContainer.vue'

// 在 vi.mock 之外定义共享状态, factory 通过闭包引用
const mockToasts = ref([])

vi.mock('../../composables/useToast.js', () => ({
  useToast: () => ({
    toasts: mockToasts,
    dismiss: (id) => {
      mockToasts.value = mockToasts.value.filter((t) => t.id !== id)
    },
    success: (msg) => {
      mockToasts.value.push({ id: Date.now(), type: 'success', message: msg })
    },
    error: (msg) => {
      mockToasts.value.push({ id: Date.now(), type: 'error', message: msg })
    },
    info: (msg) => {
      mockToasts.value.push({ id: Date.now(), type: 'info', message: msg })
    },
  }),
}))

describe('ToastContainer.vue', () => {
  /**
   * 每个测试前清空 toasts 列表,
   * 避免测试间相互污染。
   */
  beforeEach(() => {
    mockToasts.value = []
    vi.clearAllMocks()
  })

  it('无 toast — 初始状态不显示任何 toast 元素', () => {
    const wrapper = mount(ToastContainer)

    // 容器本身应渲染, 但内部没有 role="status" 的 toast 元素
    const toasts = wrapper.findAll('[role="status"]')
    expect(toasts).toHaveLength(0)
  })

  it('成功 toast — 调用 success("OK") 后渲染绿色背景 + 文本', async () => {
    const wrapper = mount(ToastContainer)

    // 直接操作共享的 mockToasts 模拟调用 success
    mockToasts.value.push({ id: 1, type: 'success', message: '操作成功' })
    await wrapper.vm.$nextTick()

    const toasts = wrapper.findAll('[role="status"]')
    expect(toasts).toHaveLength(1)
    expect(toasts[0].text()).toContain('操作成功')
    // 成功类型使用绿色背景: bg-green-500
    expect(toasts[0].classes()).toContain('bg-green-500')
  })

  it('错误 toast — 调用 error("Err") 后渲染红色背景 + 文本', async () => {
    const wrapper = mount(ToastContainer)

    mockToasts.value.push({ id: 2, type: 'error', message: '发生错误' })
    await wrapper.vm.$nextTick()

    const toasts = wrapper.findAll('[role="status"]')
    expect(toasts).toHaveLength(1)
    expect(toasts[0].text()).toContain('发生错误')
    // 错误类型使用红色背景: bg-red-500
    expect(toasts[0].classes()).toContain('bg-red-500')
  })

  it('信息 toast — 调用 info("Info") 后渲染蓝色背景 + 文本', async () => {
    const wrapper = mount(ToastContainer)

    mockToasts.value.push({ id: 3, type: 'info', message: '提示信息' })
    await wrapper.vm.$nextTick()

    const toasts = wrapper.findAll('[role="status"]')
    expect(toasts).toHaveLength(1)
    expect(toasts[0].text()).toContain('提示信息')
    // 信息类型使用蓝色背景: bg-blue-500
    expect(toasts[0].classes()).toContain('bg-blue-500')
  })

  it('关闭按钮 — 点击 X 按钮后 toast 消失', async () => {
    const wrapper = mount(ToastContainer)

    mockToasts.value.push({ id: 4, type: 'success', message: '可关闭的 toast' })
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('[role="status"]')).toHaveLength(1)

    // 点击 X 按钮 (aria-label="关闭通知")
    const closeBtn = wrapper.find('button[aria-label="关闭通知"]')
    expect(closeBtn.exists()).toBe(true)
    await closeBtn.trigger('click')
    await wrapper.vm.$nextTick()

    // toast 应消失
    expect(wrapper.findAll('[role="status"]')).toHaveLength(0)
  })
})

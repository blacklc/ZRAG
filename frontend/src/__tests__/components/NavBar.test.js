/**
 * NavBar 组件测试
 *
 * 验证顶部导航栏的默认渲染、深色模式切换、新建会话事件以及暗黑模式图标。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import NavBar from '../../components/NavBar.vue'

/**
 * 创建 NavBar 包裹器
 *
 * router-link 需要被 stub，当前测试不涉及路由实际跳转。
 *
 * @param {Object} [options={}] - 附加 mount 选项
 * @returns {Wrapper}
 */
function createWrapper(options = {}) {
  return mount(NavBar, {
    ...options,
    global: {
      stubs: {
        'router-link': {
          template: '<a><slot /></a>',
        },
      },
    },
  })
}

describe('NavBar', () => {
  /** 每个测试前清理 localStorage 与 documentElement class */
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('默认状态渲染导航链接（对话、知识库）', () => {
    const wrapper = createWrapper()
    const links = wrapper.findAll('a')
    const linkTexts = links.map((el) => el.text()).filter((t) => t.trim().length > 0)
    expect(linkTexts).toContain('对话')
    expect(linkTexts).toContain('知识库')
  })

  it('深色模式切换按钮应切换 documentElement 的 dark class', async () => {
    const wrapper = createWrapper()
    // 找到深色模式切换按钮 (aria-label="切换到深色模式")
    const toggleBtn = wrapper.findAll('button').filter(
      (btn) => btn.attributes('aria-label') === '切换到深色模式',
    )[0]
    expect(toggleBtn).toBeTruthy()

    await toggleBtn.trigger('click')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    // 再次点击切回
    const lightBtn = wrapper.findAll('button').filter(
      (btn) => btn.attributes('aria-label') === '切换到浅色模式',
    )[0]
    expect(lightBtn).toBeTruthy()
    await lightBtn.trigger('click')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('新建会话按钮应 emit new-conversation 事件', async () => {
    const wrapper = createWrapper()
    const newConvBtn = wrapper.findAll('button').filter(
      (btn) => btn.attributes('aria-label') === '新建会话',
    )[0]
    expect(newConvBtn).toBeTruthy()

    await newConvBtn.trigger('click')
    expect(wrapper.emitted('new-conversation')).toBeTruthy()
    expect(wrapper.emitted('new-conversation')).toHaveLength(1)
  })

  it('暗黑模式下按钮图标应为太阳图标 (aria-label="切换到浅色模式")', async () => {
    // 预先设置暗黑模式
    document.documentElement.classList.add('dark')
    const wrapper = createWrapper()
    // 等待 onMounted 钩子中的 isDark 更新生效
    await nextTick()

    const toggleBtn = wrapper.findAll('button').filter(
      (btn) => btn.attributes('aria-label') === '切换到浅色模式',
    )[0]
    expect(toggleBtn).toBeTruthy()
    const svg = toggleBtn.find('svg')
    expect(svg.exists()).toBe(true)
  })
})

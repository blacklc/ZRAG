/**
 * ChatSidebar 组件测试
 *
 * 验证侧边栏的渲染、空状态、会话列表选中/高亮、新建按钮、删除流程及加载状态。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatSidebar from '../../components/ChatSidebar.vue'

/**
 * 构造一条测试会话记录
 *
 * @param {string} id - 会话 ID
 * @param {string} [title] - 会话标题
 * @param {Object} [overrides={}] - 其他覆盖属性
 * @returns {Object} 会话对象
 */
function makeConv(id, title, overrides = {}) {
  return {
    id,
    title: title || `会话 ${id}`,
    created_at: '2026-06-01T00:00:00.000Z',
    last_msg_at: '2026-06-03T00:00:00.000Z',
    ...overrides,
  }
}

/**
 * 创建 ChatSidebar 包裹器
 *
 * 默认使用 Teleport stub 以便于在组件内测试弹窗内容。
 *
 * @param {Object} [props={}] - 组件 props
 * @returns {Wrapper}
 */
function createWrapper(props = {}) {
  return mount(ChatSidebar, {
    props,
    attachTo: document.body,
    global: {
      stubs: {
        Teleport: {
          template: '<div><slot /></div>',
        },
      },
    },
  })
}

describe('ChatSidebar', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('空状态: conversations=[] 时显示暂无对话', () => {
    const wrapper = createWrapper({ conversations: [] })
    const emptyEl = wrapper.find('[data-testid="sidebar-empty"]')
    expect(emptyEl.exists()).toBe(true)
    expect(emptyEl.text()).toContain('暂无对话')
  })

  it('列表渲染: 传入 2 条会话记录，渲染 2 项', () => {
    const conversations = [makeConv('1', '会话A'), makeConv('2', '会话B')]
    const wrapper = createWrapper({ conversations })
    const items = wrapper.findAll('[data-testid^="conversation-item-"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('会话A')
    expect(items[1].text()).toContain('会话B')
  })

  it('选中高亮: 设置 activeId 后对应项高亮', () => {
    const conversations = [makeConv('1', '会话A'), makeConv('2', '会话B')]
    const wrapper = createWrapper({ conversations, activeId: '1' })
    const activeItem = wrapper.find('[data-testid="conversation-item-1"]')
    expect(activeItem.exists()).toBe(true)
    // 高亮样式应包含 blue 相关类
    expect(activeItem.classes().some((c) => c.includes('blue'))).toBe(true)
  })

  it('新建按钮点击触发 new-conversation', async () => {
    const wrapper = createWrapper({ conversations: [makeConv('1')] })
    const newBtn = wrapper.find('[data-testid="new-conversation-btn"]')
    expect(newBtn.exists()).toBe(true)
    await newBtn.trigger('click')
    expect(wrapper.emitted('new-conversation')).toBeTruthy()
    expect(wrapper.emitted('new-conversation')).toHaveLength(1)
  })

  it('选择会话触发 select-conversation 事件，参数为 id', async () => {
    const conversations = [makeConv('conv-a'), makeConv('conv-b')]
    const wrapper = createWrapper({ conversations })
    const itemBtn = wrapper.find('[data-testid="conversation-item-conv-a"]').find('button')
    await itemBtn.trigger('click')
    expect(wrapper.emitted('select-conversation')).toBeTruthy()
    expect(wrapper.emitted('select-conversation')[0][0]).toBe('conv-a')
  })

  it('hover 显示删除按钮', async () => {
    const conversations = [makeConv('del-id')]
    const wrapper = createWrapper({ conversations, activeId: 'del-id' })
    const deleteBtn = wrapper.find('[data-testid="delete-btn-del-id"]')
    expect(deleteBtn.exists()).toBe(true)
  })

  it('点击删除按钮后显示确认弹窗', async () => {
    const conversations = [makeConv('del-id', '待删除对话')]
    const wrapper = createWrapper({ conversations, activeId: 'del-id' })
    const deleteBtn = wrapper.find('[data-testid="delete-btn-del-id"]')
    await deleteBtn.trigger('click')

    // 确认弹窗应该出现
    const modal = wrapper.find('[data-testid="delete-confirm-modal"]')
    expect(modal.exists()).toBe(true)
    expect(modal.text()).toContain('待删除对话')
  })

  it('取消删除后弹窗消失', async () => {
    const conversations = [makeConv('del-id', '待删除对话')]
    const wrapper = createWrapper({ conversations, activeId: 'del-id' })
    const deleteBtn = wrapper.find('[data-testid="delete-btn-del-id"]')
    await deleteBtn.trigger('click')

    const cancelBtn = wrapper.find('[data-testid="cancel-delete-btn"]')
    await cancelBtn.trigger('click')

    const modal = wrapper.find('[data-testid="delete-confirm-modal"]')
    expect(modal.exists()).toBe(false)
  })

  it('确认删除触发 delete-conversation 事件', async () => {
    const conversations = [makeConv('del-id', '待删除对话')]
    const wrapper = createWrapper({ conversations, activeId: 'del-id' })
    const deleteBtn = wrapper.find('[data-testid="delete-btn-del-id"]')
    await deleteBtn.trigger('click')

    const confirmBtn = wrapper.find('[data-testid="confirm-delete-btn"]')
    await confirmBtn.trigger('click')

    expect(wrapper.emitted('delete-conversation')).toBeTruthy()
    expect(wrapper.emitted('delete-conversation')[0][0]).toBe('del-id')
  })

  it('加载状态显示骨架屏', () => {
    const wrapper = createWrapper({ loading: true })
    const skeleton = wrapper.find('[data-testid="sidebar-skeleton"]')
    expect(skeleton.exists()).toBe(true)
  })
})

/**
 * ChatInput 组件测试
 *
 * 验证对话输入框的渲染、输入同步、键盘快捷键、禁用/加载状态以及模型选择器。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatInput from '../../components/ChatInput.vue'

/**
 * 创建 ChatInput 包裹器
 *
 * @param {Object} [props={}] - 组件 props
 * @returns {Wrapper}
 */
function createWrapper(props = {}) {
  return mount(ChatInput, {
    props,
  })
}

describe('ChatInput', () => {
  it('textarea 存在且 placeholder 正确', () => {
    const wrapper = createWrapper()
    const textarea = wrapper.find('[data-testid="chat-input-textarea"]')
    expect(textarea.exists()).toBe(true)
    expect(textarea.attributes('placeholder')).toBe('向你的知识库提问...')
  })

  it('可以接收自定义 placeholder', () => {
    const wrapper = createWrapper({ placeholder: '自定义提示' })
    const textarea = wrapper.find('[data-testid="chat-input-textarea"]')
    expect(textarea.attributes('placeholder')).toBe('自定义提示')
  })

  it('输入时触发 update:modelValue 事件', async () => {
    const wrapper = createWrapper()
    const textarea = wrapper.find('[data-testid="chat-input-textarea"]')
    await textarea.setValue('你好')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0][0]).toBe('你好')
  })

  it('Enter 发送文本', async () => {
    const wrapper = createWrapper({ modelValue: '测试问题' })
    const textarea = wrapper.find('[data-testid="chat-input-textarea"]')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: false })
    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')[0][0]).toBe('测试问题')
  })

  it('Shift+Enter 不触发 send', async () => {
    const wrapper = createWrapper({ modelValue: '测试问题' })
    const textarea = wrapper.find('[data-testid="chat-input-textarea"]')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(wrapper.emitted('send')).toBeFalsy()
  })

  it('disabled=true 时 textarea 和按钮被禁用', () => {
    const wrapper = createWrapper({ disabled: true, modelValue: '有文本' })
    const textarea = wrapper.find('[data-testid="chat-input-textarea"]')
    expect(textarea.attributes('disabled')).toBeDefined()

    const sendBtn = wrapper.find('[data-testid="chat-input-send-btn"]')
    expect(sendBtn.attributes('disabled')).toBeDefined()
  })

  it('loading=true 时按钮显示 animate-spin 图标', () => {
    const wrapper = createWrapper({ loading: true, modelValue: '有文本' })
    const spinner = wrapper.find('.animate-spin')
    expect(spinner.exists()).toBe(true)
  })

  it('空文本时发送按钮被禁用', () => {
    const wrapper = createWrapper({ modelValue: '' })
    const sendBtn = wrapper.find('[data-testid="chat-input-send-btn"]')
    expect(sendBtn.attributes('disabled')).toBeDefined()
  })

  it('非空文本时发送按钮可用', () => {
    const wrapper = createWrapper({ modelValue: '有文本' })
    const sendBtn = wrapper.find('[data-testid="chat-input-send-btn"]')
    expect(sendBtn.attributes('disabled')).toBeUndefined()
  })

  it('点击发送按钮触发 send 事件', async () => {
    const wrapper = createWrapper({ modelValue: '点击发送' })
    const sendBtn = wrapper.find('[data-testid="chat-input-send-btn"]')
    await sendBtn.trigger('click')
    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')[0][0]).toBe('点击发送')
  })

  it('模型选择器存在且包含预设选项', async () => {
    const wrapper = createWrapper()
    // 模型下拉菜单默认折叠，点击展开
    const modelSelector = wrapper.find('[data-testid="model-selector"]')
    expect(modelSelector.exists()).toBe(true)

    const toggleBtn = modelSelector.find('button')
    await toggleBtn.trigger('click')

    // 检查预设模型选项
    const optionDeepSeek = wrapper.find('[data-testid="model-option-deepseek-v4-flash"]')
    expect(optionDeepSeek.exists()).toBe(true)

    const optionSmartRouter = wrapper.find('[data-testid="model-option-smart-router"]')
    expect(optionSmartRouter.exists()).toBe(true)
  })

  it('选择模型触发 model-change 事件', async () => {
    const wrapper = createWrapper()
    const toggleBtn = wrapper.find('[data-testid="model-selector"]').find('button')
    await toggleBtn.trigger('click')

    const optionKimi = wrapper.find('[data-testid="model-option-kimi-k2.6"]')
    await optionKimi.trigger('click')

    expect(wrapper.emitted('model-change')).toBeTruthy()
    expect(wrapper.emitted('model-change')[0][0]).toBe('kimi-k2.6')
  })
})

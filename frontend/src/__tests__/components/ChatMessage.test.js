/**
 * ChatMessage.vue 组件测试
 *
 * 验证单条消息气泡的渲染逻辑:
 * - user/assistant 双样式对齐
 * - Markdown 内容渲染
 * - 来源标注
 * - 复制按钮 (hover 可见)
 * - 时间戳格式化 (HH:MM)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatMessage from '../../components/ChatMessage.vue'

// mock marked: 避免在组件初始化时执行真实的 marked.setOptions / marked.use
vi.mock('marked', () => ({
  marked: {
    parse: vi.fn((s) => `<p>${s}</p>`),
    setOptions: vi.fn(),
    use: vi.fn(),
    Renderer: function MockRenderer() {},
  },
}))

// mock DOMPurify: 避免真实的 sanitize 操作
vi.mock('dompurify', () => ({
  default: {
    sanitize: vi.fn((s) => s),
  },
}))

// mock highlight.js: 避免语言注册和 CSS 加载
vi.mock('highlight.js/lib/core', () => ({
  default: {
    registerLanguage: vi.fn(),
    getLanguage: vi.fn(() => null),
    highlightAuto: vi.fn(() => ({ value: '' })),
  },
}))

/** 用户消息 fixture */
const userMessage = Object.freeze({
  id: 'msg-user-1',
  role: 'user',
  content: 'Hello, world',
  created_at: '2025-01-01T12:00:00',
})

/** 助手消息 fixture (含来源) */
const assistantMessage = Object.freeze({
  id: 'msg-ai-1',
  role: 'assistant',
  content: '这是回答内容',
  sources: [
    { doc_title: '文档A', source_id: 'src-1', source_type: 'pdf', score: 0.95 },
    { doc_title: '文档B', source_id: 'src-2', source_type: 'web', score: 0.87 },
  ],
  created_at: '2025-01-01T12:00:05',
})

/** 助手消息 fixture (无来源) */
const assistantMessageNoSources = Object.freeze({
  id: 'msg-ai-2',
  role: 'assistant',
  content: '普通回答',
  created_at: '2025-01-01T14:30:00',
})

describe('ChatMessage.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('user 消息 — 元素具有 justify-end class 表明右对齐', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: userMessage },
    })

    const outerDiv = wrapper.find('div[data-testid="message-msg-user-1"]')
    expect(outerDiv.exists()).toBe(true)
    expect(outerDiv.classes()).toContain('justify-end')
  })

  it('assistant 消息 — 元素具有 justify-start class 表明左对齐', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: assistantMessage },
    })

    const outerDiv = wrapper.find('div[data-testid="message-msg-ai-1"]')
    expect(outerDiv.exists()).toBe(true)
    expect(outerDiv.classes()).toContain('justify-start')
  })

  it('内容渲染 — message.content 应出现在组件文本中', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: userMessage },
    })

    expect(wrapper.text()).toContain('Hello, world')
  })

  it('来源标注 — 有 sources 时渲染来源区域, 包含文档标题', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: assistantMessage },
    })

    const sourcesEl = wrapper.find('[data-testid="message-sources"]')
    expect(sourcesEl.exists()).toBe(true)
    expect(sourcesEl.text()).toContain('来源')
    expect(sourcesEl.text()).toContain('文档A')
    expect(sourcesEl.text()).toContain('文档B')
  })

  it('来源标注 — 无 sources 时不应渲染来源区域', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: userMessage },
    })

    const sourcesEl = wrapper.find('[data-testid="message-sources"]')
    expect(sourcesEl.exists()).toBe(false)
  })

  it('来源标注 — assistant 消息无 sources 时也不渲染来源区域', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: assistantMessageNoSources },
    })

    const sourcesEl = wrapper.find('[data-testid="message-sources"]')
    expect(sourcesEl.exists()).toBe(false)
  })

  it('复制按钮 — 组件中应存在复制按钮元素 (data-testid="copy-btn")', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: userMessage },
    })

    const copyBtn = wrapper.find('[data-testid="copy-btn"]')
    expect(copyBtn.exists()).toBe(true)
    expect(copyBtn.text()).toContain('复制')
  })

  it('时间戳 — created_at 被格式化为 HH:MM 格式并渲染', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: userMessage },
    })

    const timeEl = wrapper.find('[data-testid="timestamp-msg-user-1"]')
    expect(timeEl.exists()).toBe(true)
    // 2025-01-01T12:00:00 -> hours=12, minutes=00
    expect(timeEl.text()).toBe('12:00')
  })

  it('时间戳 — assistant 消息的时间戳也应格式化为 HH:MM', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: assistantMessage },
    })

    const timeEl = wrapper.find('[data-testid="timestamp-msg-ai-1"]')
    expect(timeEl.exists()).toBe(true)
    // 2025-01-01T12:00:05 -> hours=12, minutes=00
    expect(timeEl.text()).toBe('12:00')
  })
})

/**
 * 聊天业务逻辑 composable
 *
 * 封装会话列表、消息、发送状态的完整生命周期:
 *   - 加载会话列表 / 消息列表
 *   - 创建新会话 (含首轮 RAG 问答)
 *   - 追加消息到已有会话
 *   - 删除会话并清理本地状态
 *   - 乐观更新与失败回滚
 *
 * 此模块对应 QA Q33 中规划的 useChat + useConversation,
 * 将 ChatView.vue 中的核心业务逻辑分离到可独立测试的复合体中。
 */

import { ref, computed } from 'vue'
import {
  listConversations,
  createConversation,
  getMessages,
  addMessage,
  deleteConversation,
} from '../api/endpoints.js'
import { getUserMessage } from '../api/index.js'
import { useToast } from './useToast.js'

const toast = useToast()

/**
 * 创建并返回聊天业务逻辑复合体
 *
 * @returns {{
 *   conversations: import('vue').Ref,
 *   activeConversationId: import('vue').Ref,
 *   messages: import('vue').Ref,
 *   conversationsLoading: import('vue').Ref,
 *   messagesLoading: import('vue').Ref,
 *   sending: import('vue').Ref,
 *   activeConversation: import('vue').ComputedRef,
 *   loadConversations: () => Promise<void>,
 *   loadMessages: (id: string) => Promise<void>,
 *   selectConversation: (id: string) => Promise<void>,
 *   sendMessage: (query: string) => Promise<void>,
 *   deleteConversation: (id: string) => Promise<void>,
 *   resetConversation: () => void,
 * }}
 */
export function useChat() {
  /** 会话列表 */
  const conversations = ref([])
  /** 当前激活的会话 ID; null 表示未选中 */
  const activeConversationId = ref(null)
  /** 当前会话的消息列表 */
  const messages = ref([])
  /** 会话列表加载状态 */
  const conversationsLoading = ref(false)
  /** 消息加载状态 */
  const messagesLoading = ref(false)
  /** 发送中状态 (含 AI 思考阶段) */
  const sending = ref(false)

  /** 当前激活的会话对象 (来自 conversations 列表) */
  const activeConversation = computed(() => {
    if (!activeConversationId.value) return null
    return conversations.value.find((c) => c.id === activeConversationId.value) || null
  })

  /**
   * 加载会话列表
   * - 设置 conversationsLoading
   * - 失败时弹出错误 toast
   *
   * @returns {Promise<void>}
   */
  async function loadConversations() {
    conversationsLoading.value = true
    try {
      const data = await listConversations()
      conversations.value = data?.conversations || []
    } catch (e) {
      toast.error(`加载会话列表失败: ${getUserMessage(e)}`)
      conversations.value = []
    } finally {
      conversationsLoading.value = false
    }
  }

  /**
   * 加载指定会话的消息列表
   *
   * @param {string} conversationId - 会话 ID
   * @returns {Promise<void>}
   */
  async function loadMessages(conversationId) {
    messagesLoading.value = true
    try {
      const data = await getMessages(conversationId)
      messages.value = data?.messages || []
      return data
    } catch (e) {
      toast.error(`加载消息失败: ${getUserMessage(e)}`)
      messages.value = []
    } finally {
      messagesLoading.value = false
    }
  }

  /**
   * 选中某个会话并加载消息
   *
   * @param {string} id - 会话 ID
   * @returns {Promise<void>}
   */
  async function selectConversation(id) {
    if (!id || id === activeConversationId.value) return
    activeConversationId.value = id
    await loadMessages(id)
  }

  /**
   * 重置到"新建会话"状态 (不清除 conversations 列表)
   *
   * @returns {void}
   */
  function resetConversation() {
    activeConversationId.value = null
    messages.value = []
  }

  /**
   * 发送消息 — 根据是否有激活会话选择 create 或 append
   * - 乐观追加临时用户消息
   * - 成功后: 重新拉取消息和会话列表以获取后端最新状态
   * - 失败时: Toast 通知 + 保留用户消息 + 追加内联错误消息
   *
   * @param {string} query - 已 trim 的查询文本
   * @returns {Promise<void>}
   */
  async function sendMessage(query) {
    const text = (query || '').trim()
    if (!text) return

    // 乐观追加临时用户消息
    const tempUserMsg = {
      id: `temp-user-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    messages.value = [...messages.value, tempUserMsg]
    sending.value = true

    try {
      if (activeConversationId.value) {
        await addMessage(activeConversationId.value, text)
        await loadMessages(activeConversationId.value)
        await loadConversations()
      } else {
        const conv = await createConversation(text)
        const newId = conv?.conversation_id
        if (!newId) {
          throw new Error('后端未返回会话 ID')
        }
        activeConversationId.value = newId
        await loadMessages(newId)
        await loadConversations()
      }
    } catch (e) {
      const errorMsg = getUserMessage(e)
      toast.error(`发送失败: ${errorMsg}`)
      // 保留临时用户消息 + 追加内联错误消息
      messages.value = [...messages.value, {
        id: `error-${Date.now()}`,
        role: 'error',
        content: errorMsg,
        created_at: new Date().toISOString(),
      }]
    } finally {
      sending.value = false
    }
  }

  /**
   * 删除指定会话
   * - 调用 API 删除
   * - 从本地列表中移除
   * - 若删除的是当前激活会话, 清空右侧
   *
   * @param {string} id - 会话 ID
   * @returns {Promise<void>}
   */
  async function removeConversation(id) {
    let serverDeleted = false
    try {
      await deleteConversation(id)
      serverDeleted = true
    } catch (e) {
      if (e?.status === 429) {
        toast.error('请求过于频繁，请稍后重试')
      } else {
        toast.error(`删除会话失败: ${getUserMessage(e)}`)
        return
      }
    }
    const idx = conversations.value.findIndex((c) => c.id === id)
    if (idx >= 0) {
      conversations.value.splice(idx, 1)
    }
    if (activeConversationId.value === id) {
      activeConversationId.value = null
      messages.value = []
    }
    toast.success('会话已删除')
  }

  return {
    conversations,
    activeConversationId,
    messages,
    conversationsLoading,
    messagesLoading,
    sending,
    activeConversation,
    loadConversations,
    loadMessages,
    selectConversation,
    sendMessage,
    deleteConversation: removeConversation,
    resetConversation,
  }
}

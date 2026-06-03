<!--
  ChatView 页面
  聊天主页面: 负责组装 NavBar + Sidebar + 消息区 + Input,
  维护会话状态/消息状态/输入状态,并处理滚动与特殊 UI 状态.
  遵循 Apple 风格设计: 简洁的视觉层次 + 平滑过渡.
-->
<template>
  <div class="flex flex-col h-screen overflow-hidden bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <!-- 顶部导航栏 -->
    <NavBar @new-conversation="handleNewConversation" />

    <!-- 主体区域: 左侧侧边栏 + 右侧对话区 -->
    <div class="flex flex-1 min-h-0">
      <!-- 左侧: 会话列表 (260px 固定宽度) -->
      <div class="w-[260px] flex-shrink-0">
        <ChatSidebar
          :conversations="conversations"
          :active-id="activeConversationId"
          :loading="conversationsLoading"
          @new-conversation="handleNewConversation"
          @select-conversation="handleSelectConversation"
          @delete-conversation="handleDeleteConversation"
        />
      </div>

      <!-- 右侧: 对话主区 -->
      <main class="flex-1 flex flex-col min-w-0">
        <!-- 顶部: 当前会话标题 -->
        <header
          class="h-12 flex items-center px-6
                 border-b border-gray-200 dark:border-gray-800
                 bg-white/70 dark:bg-gray-900/70 backdrop-blur-md
                 text-sm font-medium"
          data-testid="chat-header"
        >
          <h1 class="truncate" :title="currentTitle">
            {{ currentTitle }}
          </h1>
        </header>

        <!-- 中间: 消息列表 (可滚动) -->
        <div
          ref="messagesContainerRef"
          class="flex-1 overflow-y-auto px-4 py-6"
          data-testid="messages-container"
        >
          <!-- 空状态: 无激活会话 -->
          <div
            v-if="!activeConversationId"
            class="h-full flex flex-col items-center justify-center text-center"
            data-testid="empty-state"
          >
            <div
              class="text-6xl font-bold tracking-tight
                     bg-gradient-to-r from-blue-500 to-indigo-600
                     bg-clip-text text-transparent select-none"
              aria-hidden="true"
            >
              ZRAG
            </div>
            <p class="mt-4 text-base text-gray-600 dark:text-gray-400">
              向你的知识库提问
            </p>
            <p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
              在下方输入框中输入你的问题即可开始
            </p>
          </div>

          <!-- 有激活会话 -->
          <div v-else class="max-w-3xl mx-auto space-y-4">
            <!-- 加载中: 消息骨架 -->
            <div
              v-if="messagesLoading"
              class="space-y-4"
              data-testid="messages-loading"
            >
              <div
                v-for="i in 3"
                :key="`skel-${i}`"
                class="flex"
                :class="i % 2 === 0 ? 'justify-start' : 'justify-end'"
              >
                <div
                  class="max-w-2xl px-4 py-3 rounded-lg shadow-sm
                         bg-gray-100 dark:bg-gray-800 animate-pulse"
                >
                  <div class="h-3 w-48 bg-gray-300 dark:bg-gray-600 rounded"></div>
                  <div class="h-3 w-32 mt-2 bg-gray-200 dark:bg-gray-500 rounded"></div>
                </div>
              </div>
            </div>

            <!-- 消息列表 -->
            <template v-else>
              <ChatMessage
                v-for="msg in messages"
                :key="msg.id"
                :message="msg"
              />

              <!-- AI 思考中: 跳动三点 -->
              <div
                v-if="sending"
                class="flex justify-start"
                data-testid="typing-indicator"
              >
                <div
                  class="px-4 py-3 rounded-lg shadow-sm
                         bg-gray-100 dark:bg-gray-800
                         rounded-bl-sm"
                >
                  <div class="flex items-center gap-1.5">
                    <span
                      v-for="i in 3"
                      :key="i"
                      class="block w-2 h-2 rounded-full bg-gray-400 dark:bg-gray-500 typing-dot"
                      :style="{ animationDelay: `${(i - 1) * 0.15}s` }"
                    />
                  </div>
                </div>
              </div>
            </template>

            <!-- 滚动锚点: 配合 scrollIntoView -->
            <div ref="scrollAnchorRef" aria-hidden="true"></div>
          </div>
        </div>

        <!-- 底部: 输入区 (sticky) -->
        <ChatInput
          v-model="inputText"
          :model="selectedModel"
          :disabled="sending"
          :loading="sending"
          :placeholder="inputPlaceholder"
          @send="handleSend"
          @model-change="handleModelChange"
        />
      </main>
    </div>
  </div>
</template>

<script setup>
/**
 * ChatView 页面
 *
 * 聊天主页面, 负责将各子组件组装为一个完整对话界面.
 * 维护的核心状态:
 * - conversations: 会话列表
 * - activeConversationId: 当前激活的会话 ID
 * - messages: 当前会话的消息列表
 * - inputText: 输入框文本 (v-model)
 * - selectedModel: 当前选中的模型
 * - conversationsLoading: 会话列表加载状态
 * - messagesLoading: 消息加载状态
 * - sending: 发送中状态
 *
 * 关键行为:
 * - 挂载时拉取会话列表
 * - 选中会话: 加载该会话消息
 * - 发送消息: 第一次创建会话, 后续追加消息
 * - 删除会话: 调用接口并清理本地状态
 * - 新消息到达时自动滚动到底部
 */
import { ref, computed, onMounted, nextTick } from 'vue'
import NavBar from '../components/NavBar.vue'
import ChatSidebar from '../components/ChatSidebar.vue'
import ChatMessage from '../components/ChatMessage.vue'
import ChatInput from '../components/ChatInput.vue'
import {
  listConversations,
  createConversation,
  getMessages,
  addMessage,
  deleteConversation,
} from '../api/endpoints.js'
import { useToast } from '../composables/useToast.js'

// ======================
// Toast
// ======================
const toast = useToast()

// ======================
// 响应式状态
// ======================

/** 会话列表 */
const conversations = ref([])
/** 当前激活的会话 ID; null 表示未选中 */
const activeConversationId = ref(null)
/** 当前会话的消息列表 */
const messages = ref([])
/** 输入框文本 (v-model) */
const inputText = ref('')
/** 选中的模型; 默认 smart-router */
const selectedModel = ref('smart-router')
/** 会话列表加载状态 */
const conversationsLoading = ref(false)
/** 消息加载状态 */
const messagesLoading = ref(false)
/** 发送中状态 (含 AI 思考阶段) */
const sending = ref(false)

// ======================
// 模板引用
// ======================
/** 消息容器 DOM, 用于 nextTick 后再定位 scrollAnchor */
const messagesContainerRef = ref(null)
/** 消息列表底部的滚动锚点 */
const scrollAnchorRef = ref(null)

// ======================
// 计算属性
// ======================

/** 当前激活的会话对象 (来自 conversations 列表) */
const activeConversation = computed(() => {
  if (!activeConversationId.value) return null
  return conversations.value.find((c) => c.id === activeConversationId.value) || null
})

/** 顶部标题: 有会话时显示其标题, 否则显示"新对话" */
const currentTitle = computed(() => {
  return activeConversation.value?.title || '新对话'
})

/** 输入框 placeholder: 根据是否有激活会话区分 */
const inputPlaceholder = computed(() => {
  return activeConversationId.value
    ? '继续提问...'
    : '向你的知识库提问...'
})

// ======================
// 生命周期
// ======================

/**
 * 页面挂载时拉取会话列表
 * 失败时使用 toast.error 反馈, 但不阻塞后续交互
 */
onMounted(async () => {
  await loadConversations()
})

// ======================
// 工具方法
// ======================

/**
 * 滚动消息列表到底部
 * - 通过 nextTick 等待 DOM 更新完成
 * - 优先使用 scrollIntoView, 兼容性最好
 * - 失败 (容器尚未挂载) 时静默处理
 */
async function scrollToBottom() {
  await nextTick()
  const anchor = scrollAnchorRef.value
  if (anchor && typeof anchor.scrollIntoView === 'function') {
    anchor.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }
}

/**
 * 加载会话列表
 * - 设置 conversationsLoading
 * - 失败时弹出错误 toast
 */
async function loadConversations() {
  conversationsLoading.value = true
  try {
    const list = await listConversations()
    conversations.value = Array.isArray(list) ? list : []
  } catch (e) {
    toast.error(`加载会话列表失败: ${e?.message || '未知错误'}`)
    conversations.value = []
  } finally {
    conversationsLoading.value = false
  }
}

/**
 * 加载指定会话的消息列表
 * @param {string} conversationId 会话 ID
 */
async function loadMessages(conversationId) {
  messagesLoading.value = true
  try {
    const list = await getMessages(conversationId)
    messages.value = Array.isArray(list) ? list : []
    await scrollToBottom()
  } catch (e) {
    toast.error(`加载消息失败: ${e?.message || '未知错误'}`)
    messages.value = []
  } finally {
    messagesLoading.value = false
  }
}

// ======================
// 事件处理
// ======================

/**
 * 处理"新建会话"
 * 业务语义: 清空当前选择, 让用户输入第一条消息来触发 createConversation
 * 这里只重置 UI 状态, 不调用任何接口.
 */
function handleNewConversation() {
  activeConversationId.value = null
  messages.value = []
  inputText.value = ''
}

/**
 * 处理"选择会话"
 * @param {string} id 会话 ID
 */
async function handleSelectConversation(id) {
  if (!id || id === activeConversationId.value) return
  activeConversationId.value = id
  await loadMessages(id)
}

/**
 * 处理"删除会话"
 * @param {string} id 会话 ID
 */
async function handleDeleteConversation(id) {
  try {
    await deleteConversation(id)
  } catch (e) {
    toast.error(`删除会话失败: ${e?.message || '未知错误'}`)
    return
  }
  // 从本地列表中移除
  const idx = conversations.value.findIndex((c) => c.id === id)
  if (idx >= 0) {
    conversations.value.splice(idx, 1)
  }
  // 如果删除的是当前激活会话, 清空右侧
  if (activeConversationId.value === id) {
    activeConversationId.value = null
    messages.value = []
  }
  toast.success('会话已删除')
}

/**
 * 处理"发送消息"
 * - 没有激活会话: 调 createConversation(query) 创建会话, 加载消息, 选中新会话
 * - 已有会话: 调 addMessage(conversationId, query) 追加消息
 * @param {string} query 用户提交的查询文本 (已 trim)
 */
async function handleSend(query) {
  const text = (query || '').trim()
  if (!text) return

  // 立即将用户消息追加到本地 (乐观更新)
  const tempUserMsg = {
    id: `temp-user-${Date.now()}`,
    role: 'user',
    content: text,
    created_at: new Date().toISOString(),
  }
  messages.value = [...messages.value, tempUserMsg]
  inputText.value = ''

  sending.value = true
  await scrollToBottom()

  try {
    if (!activeConversationId.value) {
      // 第一次: 创建会话
      const conv = await createConversation(text)
      const newId = conv?.id
      if (!newId) {
        throw new Error('后端未返回会话 ID')
      }
      // 选中新会话
      activeConversationId.value = newId
      // 重新拉取该会话的消息 (含后端可能返回的 user + assistant 完整消息)
      await loadMessages(newId)
      // 刷新侧边栏列表 (后端可能会按时间排序)
      await loadConversations()
    } else {
      // 后续: 追加消息
      await addMessage(activeConversationId.value, text)
      // 重新拉取消息以获取后端可能返回的最新状态
      await loadMessages(activeConversationId.value)
      // 刷新侧边栏以更新 last_msg_at / title 等
      await loadConversations()
    }
  } catch (e) {
    toast.error(`发送失败: ${e?.message || '未知错误'}`)
    // 回滚本地乐观追加
    messages.value = messages.value.filter((m) => m.id !== tempUserMsg.id)
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}

/**
 * 处理"模型切换"
 * @param {string} value 新的模型标识
 */
function handleModelChange(value) {
  if (value) {
    selectedModel.value = value
  }
}
</script>

<style>
/*
  三个跳动的小圆点 (typing indicator) 动画
  - 使用 transform/opacity 提升性能
  - 错开 animation-delay 形成"波浪"效果
*/
.typing-dot {
  animation: typing-bounce 1.2s ease-in-out infinite;
}

@keyframes typing-bounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}
</style>

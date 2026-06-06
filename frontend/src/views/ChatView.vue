<!--
  ChatView 页面

  对话主页面 - 切片 38 业务 + 切片 41 响应式合并实现:
  - 顶部 NavBar: logo + 导航 + 深色模式 + 新建会话 + (移动端) 侧边栏切换
  - 左侧 ChatSidebar: 会话历史列表
  - 中部主区域: 消息流 + 输入区
  - 响应式布局:
    * 桌面 (>=1024px): 侧边栏常驻展开 (260px)
    * 平板  (768-1023px): 侧边栏可折叠
    * 手机  (<768px): 侧边栏默认隐藏, 由 NavBar 汉堡按钮触发半屏覆盖
  - 暗黑模式自适应
-->
<template>
  <div class="h-screen flex flex-col bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <!-- 顶部导航栏 (含移动端侧边栏切换) -->
    <NavBar :show-sidebar-toggle="true" @toggle-sidebar="toggleMobileSidebar" @new-conversation="handleNewConversation" />

    <!-- 主体: 侧边栏 + 主内容 -->
    <div class="flex flex-1 min-h-0 relative">
      <!-- 移动端侧边栏背景遮罩 -->
      <div
        v-if="mobileSidebarOpen"
        class="md:hidden fixed inset-0 z-30 bg-black/40 backdrop-blur-sm"
        data-testid="sidebar-backdrop"
        @click="closeMobileSidebar"
      ></div>

      <!--
        侧边栏容器:
        - 桌面 (>=md): relative + translate-x-0 常驻
        - 移动 (<md): fixed 定位, 通过 translate-x 切换
      -->
      <div
        class="md:relative md:translate-x-0
               fixed inset-y-0 left-0 z-40
               transition-transform duration-200 ease-in-out
               top-14 md:top-0
               bottom-0 md:bottom-auto
               w-[260px] flex-shrink-0"
        :class="mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'"
        data-testid="sidebar-container"
      >
        <ChatSidebar
          :conversations="conversations"
          :active-id="activeConversationId"
          :loading="conversationsLoading"
          @new-conversation="handleNewConversation"
          @select-conversation="handleSelectConversation"
          @delete-conversation="handleDeleteConversation"
        />
      </div>

      <!-- 主内容区 -->
      <main class="flex-1 flex flex-col min-w-0">
        <!-- 桌面端顶部: 当前会话标题 -->
        <header
          class="hidden md:flex h-12 items-center px-6
                 border-b border-gray-200 dark:border-gray-800
                 bg-white/70 dark:bg-gray-900/70 backdrop-blur-md
                 text-sm font-medium"
          data-testid="chat-header"
        >
          <h1 class="truncate" :title="currentTitle">
            {{ currentTitle }}
          </h1>
        </header>

        <!--
          移动端顶部条: 显示当前会话标题 (Tab 模式).
          桌面端隐藏 (由 header 直接显示).
        -->
        <div
          v-if="currentTitle"
          class="md:hidden px-4 py-2 text-sm font-medium
                 border-b border-gray-200 dark:border-gray-800
                 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md
                 truncate"
          data-testid="mobile-current-title"
        >
          {{ currentTitle }}
        </div>

        <!-- 中间: 消息列表 (可滚动) -->
        <div
          ref="messagesContainerRef"
          class="flex-1 overflow-y-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6"
          data-testid="messages-container"
        >
          <div class="max-w-3xl mx-auto space-y-3 sm:space-y-4">
            <!-- 空状态: 无激活会话且未发送 -->
            <div
              v-if="!activeConversationId && !sending && messages.length === 0"
              class="h-full flex flex-col items-center justify-center text-center px-4"
              data-testid="chat-empty"
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

            <!-- 发送中但无激活会话: 加载指示器 -->
            <div
              v-else-if="!activeConversationId && sending"
              class="h-full flex flex-col items-center justify-center text-center px-4"
              data-testid="chat-sending"
            >
              <div
                class="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"
              ></div>
              <p class="mt-4 text-sm text-gray-500 dark:text-gray-400">
                正在思考...
              </p>
            </div>

            <!-- 有激活会话 -->
            <template v-else>
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
            </template>
          </div>
        </div>

        <!-- 底部: 输入区 (sticky) -->
        <ChatInput
          ref="chatInputRef"
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
 * 对话主页面, 负责将各子组件组装为一个完整对话界面.
 * 维护的核心状态:
 * - conversations: 会话列表
 * - activeConversationId: 当前激活的会话 ID
 * - messages: 当前会话的消息列表
 * - inputText: 输入框文本 (v-model)
 * - selectedModel: 当前选中的模型
 * - conversationsLoading: 会话列表加载状态
 * - messagesLoading: 消息加载状态
 * - sending: 发送中状态 (含 AI 思考阶段)
 * - mobileSidebarOpen: 移动端侧边栏开关
 *
 * 关键行为:
 * - 挂载时拉取会话列表
 * - 选中会话: 加载该会话消息
 * - 发送消息: 第一次创建会话, 后续追加消息
 * - 删除会话: 调用接口并清理本地状态
 * - 新消息到达时自动滚动到底部
 * - 移动端: NavBar 汉堡按钮触发侧边栏覆盖层
 */
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import NavBar from '../components/NavBar.vue'
import ChatSidebar from '../components/ChatSidebar.vue'
import ChatMessage from '../components/ChatMessage.vue'
import ChatInput from '../components/ChatInput.vue'
import { useChat } from '../composables/useChat.js'

/** Tailwind 'md' 断点 (像素), 与 NavBar 保持一致 */
const MD_BREAKPOINT_PX = 768
/** 默认会话标题 (当会话未命名时显示) */
const DEFAULT_CONVERSATION_TITLE = '新对话'
/** 默认选中的模型标识 */
const DEFAULT_MODEL = 'smart-router'

// ---- 业务逻辑 (useChat composable) ----
const {
  conversations,
  activeConversationId,
  messages,
  conversationsLoading,
  messagesLoading,
  sending,
  activeConversation,
  loadConversations,
  selectConversation,
  sendMessage,
  deleteConversation,
  resetConversation,
} = useChat()

// ---- UI 状态 (ChatView 专属) ----
/** 输入框文本 (v-model) */
const inputText = ref('')
/** ChatInput 组件引用 (用于聚焦) */
const chatInputRef = ref(null)
/** 选中的模型; 默认 smart-router */
const selectedModel = ref(DEFAULT_MODEL)
/** 移动端侧边栏开关 */
const mobileSidebarOpen = ref(false)
/** 消息容器 DOM, 用于 nextTick 后再定位 scrollAnchor */
const messagesContainerRef = ref(null)
/** 消息列表底部的滚动锚点 */
const scrollAnchorRef = ref(null)

// ---- Computed ----
/** 顶部标题: 有会话时显示其标题, 否则显示"新对话" */
const currentTitle = computed(() => {
  return activeConversation.value?.title || DEFAULT_CONVERSATION_TITLE
})

/** 输入框 placeholder: 根据是否有激活会话区分 */
const inputPlaceholder = computed(() => {
  return activeConversationId.value
    ? '继续提问...'
    : '向你的知识库提问...'
})

// ---- 生命周期 ----
onMounted(async () => {
  await loadConversations()
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', onResize)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', onResize)
  }
})

// ---- UI 事件处理 ----

/** 窗口 resize 时, >=md 自动关闭移动端侧边栏 */
function onResize() {
  if (typeof window === 'undefined') return
  if (window.innerWidth >= MD_BREAKPOINT_PX) {
    mobileSidebarOpen.value = false
  }
}

function toggleMobileSidebar() {
  mobileSidebarOpen.value = !mobileSidebarOpen.value
}

function closeMobileSidebar() {
  mobileSidebarOpen.value = false
}

/** 滚动到消息底部 */
async function scrollToBottom() {
  await nextTick()
  const anchor = scrollAnchorRef.value
  if (anchor && typeof anchor.scrollIntoView === 'function') {
    anchor.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }
}

/** 新建会话: 重置 UI 状态 + 聚焦输入框 */
function handleNewConversation() {
  resetConversation()
  inputText.value = ''
  mobileSidebarOpen.value = false
  chatInputRef.value?.focus()
}

/** 选中会话: 加载消息 + 滚动到底部 */
async function handleSelectConversation(id) {
  if (!id || id === activeConversationId.value) return
  mobileSidebarOpen.value = false
  await selectConversation(id)
  await scrollToBottom()
}

/** 删除会话 */
async function handleDeleteConversation(id) {
  await deleteConversation(id)
}

/** 发送消息: 清空输入框 → 调 sendMessage → 滚动到底部 */
async function handleSend(query) {
  const text = (query || '').trim()
  if (!text) return
  inputText.value = ''
  await scrollToBottom()
  await sendMessage(text)
  await scrollToBottom()
}

/** 模型切换 */
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

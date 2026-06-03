<!--
  ChatView 页面
  对话主页面 - 切片 38/41 共建:
  - 顶部 NavBar: logo + 导航 + 深色模式 + 新建会话 + (移动端) 侧边栏切换
  - 左侧 ChatSidebar: 会话历史列表
  - 中部主区域: 消息流 + 输入区
  - 响应式布局:
    * 桌面 (>=1024px): 侧边栏常驻展开 (260px)
    * 平板  (768-1023px): 侧边栏可折叠 (默认展开, 通过自身按钮收起)
    * 手机  (<768px): 侧边栏默认隐藏, 由 NavBar 汉堡按钮触发半屏覆盖
  - 暗黑模式自适应
-->
<template>
  <div
    class="h-screen flex flex-col bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
  >
    <!-- 顶部导航栏 (含移动端侧边栏切换) -->
    <NavBar :show-sidebar-toggle="true" @toggle-sidebar="toggleMobileSidebar" />

    <!-- 主体: 侧边栏 + 主内容 -->
    <div class="flex-1 flex overflow-hidden relative">
      <!-- 侧边栏 (移动端背景遮罩) -->
      <div
        v-if="mobileSidebarOpen"
        class="md:hidden fixed inset-0 z-30 bg-black/40 backdrop-blur-sm"
        data-testid="sidebar-backdrop"
        @click="closeMobileSidebar"
      ></div>

      <!--
        侧边栏容器:
        - 桌面: 始终可见 (受 ChatSidebar 内部 collapsed 控制)
        - 移动: 切换为 fixed 定位覆盖层
      -->
      <div
        class="md:relative md:translate-x-0
               fixed inset-y-0 left-0 z-40
               transition-transform duration-200 ease-in-out
               top-14 md:top-0
               bottom-0 md:bottom-auto"
        :class="mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'"
        data-testid="sidebar-container"
      >
        <ChatSidebar
          :conversations="conversations"
          :active-id="activeId"
          :loading="loading"
          @new-conversation="handleNewConversation"
          @select-conversation="handleSelect"
          @delete-conversation="handleDelete"
        />
      </div>

      <!-- 主内容区 -->
      <main class="flex-1 flex flex-col min-w-0">
        <!--
          移动端顶部条: 显示当前会话标题 (Tab 模式) 或提示.
          桌面端隐藏 (由 ChatSidebar 直接显示标题).
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

        <!-- 消息流 -->
        <div
          ref="messagesContainer"
          class="flex-1 overflow-y-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6"
          data-testid="messages-container"
        >
          <div class="max-w-3xl mx-auto space-y-3 sm:space-y-4">
            <!-- 空状态: 未选择会话时显示欢迎语 -->
            <div
              v-if="!activeId"
              class="flex flex-col items-center justify-center h-full min-h-[60vh] text-center px-4"
              data-testid="chat-empty"
            >
              <div class="text-4xl sm:text-5xl mb-3">💬</div>
              <h2 class="text-lg sm:text-xl font-semibold">开始一段新对话</h2>
              <p class="mt-2 text-sm text-gray-500 dark:text-gray-400 max-w-md">
                在下方输入你的问题,系统将基于知识库中的文档为你生成回答.
              </p>
            </div>

            <!-- 消息列表 (待切片 38 接入) -->
            <template v-else>
              <div
                v-if="messages.length === 0"
                class="flex flex-col items-center justify-center min-h-[40vh] text-center text-sm text-gray-500 dark:text-gray-400"
                data-testid="chat-loading"
              >
                正在加载消息...
              </div>
              <ChatMessage
                v-for="msg in messages"
                :key="msg.id"
                :message="msg"
              />
            </template>
          </div>
        </div>

        <!-- 输入区 -->
        <ChatInput
          v-model="input"
          :model="model"
          :loading="sending"
          :disabled="!activeId && !canStartNew"
          @send="handleSend"
          @model-change="(v) => (model = v)"
        />
      </main>
    </div>
  </div>
</template>

<script setup>
/**
 * ChatView 页面
 *
 * 对话主页面 - 切片 38/41 共同实现:
 * - 切片 38 负责: 会话/消息/发送的完整业务逻辑
 * - 切片 41 负责: 桌面/平板/手机三种尺寸下的响应式布局
 *
 * 当前 (切片 41) 实现:
 * - 完整的响应式结构 (Sidebar / Main / Input)
 * - 移动端汉堡按钮触发半屏覆盖式侧边栏
 * - 桌面端侧边栏常驻展开
 * - 占位的消息列表 / 空状态 / 输入区
 *
 * 业务状态 (conversations / messages / activeId 等) 暂时使用本地 ref,
 * 切片 38 将补充与后端 listConversations / getMessages / addMessage 的真实联动.
 */
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import NavBar from '../components/NavBar.vue'
import ChatSidebar from '../components/ChatSidebar.vue'
import ChatMessage from '../components/ChatMessage.vue'
import ChatInput from '../components/ChatInput.vue'

// ======================
// 响应式状态 (业务)
// ======================
/** 会话列表数据 */
const conversations = ref([])
/** 当前激活会话 ID */
const activeId = ref(null)
/** 当前激活会话的标题 (移动端顶部条使用) */
const currentTitle = computed(() => {
  if (!activeId.value) return ''
  const c = conversations.value.find((x) => x.id === activeId.value)
  return c ? (c.title || '新对话') : ''
})
/** 会话列表加载状态 */
const loading = ref(false)
/** 消息列表 */
const messages = ref([])
/** 输入框文本 */
const input = ref('')
/** 选中的模型 */
const model = ref('smart-router')
/** 发送中状态 */
const sending = ref(false)
/** 消息容器 DOM 引用 (用于发送后滚动到底部) */
const messagesContainer = ref(null)

// ======================
// 响应式状态 (布局)
// ======================
/**
 * 移动端侧边栏开关
 * - 桌面端 (>=md): 通过 CSS 直接 translate, 此 ref 仅作为初始状态.
 * - 移动端: 由 NavBar 的 toggle-sidebar 事件控制.
 */
const mobileSidebarOpen = ref(false)

/** 是否允许"无会话时直接开始新对话" */
const canStartNew = ref(true)

// ======================
// 业务方法
// ======================

/**
 * 切换移动端侧边栏
 * 仅在 <md 时由 NavBar 的汉堡按钮触发
 */
function toggleMobileSidebar() {
  mobileSidebarOpen.value = !mobileSidebarOpen.value
}

/**
 * 关闭移动端侧边栏 (点击遮罩)
 */
function closeMobileSidebar() {
  mobileSidebarOpen.value = false
}

/**
 * 处理"新建会话"事件
 * 切片 38 将调用 createConversation API, 这里仅占位.
 */
function handleNewConversation() {
  // 关闭移动端菜单
  mobileSidebarOpen.value = false
  // 切片 38: 实际调用 createConversation 后激活
  activeId.value = null
  messages.value = []
}

/**
 * 处理"选择会话"事件
 * 切片 38 将调用 getMessages API 加载历史消息.
 */
function handleSelect(id) {
  activeId.value = id
  messages.value = []
  mobileSidebarOpen.value = false
}

/**
 * 处理"删除会话"事件
 * 切片 38 将调用 deleteConversation API.
 */
function handleDelete(id) {
  conversations.value = conversations.value.filter((c) => c.id !== id)
  if (activeId.value === id) {
    activeId.value = null
    messages.value = []
  }
}

/**
 * 处理"发送"事件
 * 切片 38 将调用 addMessage API 触发 RAG 问答流程.
 */
async function handleSend(query) {
  if (sending.value) return
  // 切片 38: 调用 addMessage; 当前仅占位
  input.value = ''
  await nextTick()
  scrollToBottom()
}

/**
 * 滚动消息容器到底部
 * 用于发送新消息后或加载历史后, 保持最新消息可见.
 */
function scrollToBottom() {
  if (!messagesContainer.value) return
  messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
}

// 监听消息列表变化, 自动滚到底部
watch(
  () => messages.value.length,
  () => {
    nextTick(scrollToBottom)
  },
)

/**
 * 监听窗口尺寸变化: 在 >=md 时强制关闭移动菜单状态
 * 避免从桌面缩到移动端时, 侧边栏还停留在"打开"状态.
 */
function onResize() {
  if (typeof window === 'undefined') return
  if (window.innerWidth >= 768) {
    mobileSidebarOpen.value = false
  }
}

// 挂载时绑定 resize 监听
onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', onResize)
  }
})
</script>

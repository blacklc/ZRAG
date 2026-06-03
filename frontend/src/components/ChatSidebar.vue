<template>
  <aside
    class="flex flex-col h-full bg-gray-50 dark:bg-gray-800
           border-r border-gray-200 dark:border-gray-700
           transition-all duration-200
           md:w-64 md:shrink-0"
    :class="collapsed ? 'w-12' : 'w-64'"
  >
    <!-- 顶部区域：折叠按钮 + 新建对话 -->
    <div class="flex items-center gap-1 p-2 border-b border-gray-200 dark:border-gray-700">
      <button
        type="button"
        class="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="toggleCollapsed"
      >
        <!-- 折叠/展开图标 -->
        <svg
          v-if="!collapsed"
          xmlns="http://www.w3.org/2000/svg"
          class="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
        </svg>
        <svg
          v-else
          xmlns="http://www.w3.org/2000/svg"
          class="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
        </svg>
      </button>
      <button
        v-if="!collapsed"
        type="button"
        class="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        data-testid="new-conversation-btn"
        @click="handleNewConversation"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        新建对话
      </button>
    </div>

    <!-- 会话列表区域 -->
    <div v-if="!collapsed" class="flex-1 overflow-y-auto">
      <!-- 加载状态：骨架屏 -->
      <ul v-if="loading" class="space-y-2 p-2" data-testid="sidebar-skeleton">
        <li
          v-for="i in 5"
          :key="i"
          class="p-3 rounded-md bg-gray-100 dark:bg-gray-700 animate-pulse"
        >
          <div class="h-3.5 w-3/4 bg-gray-300 dark:bg-gray-600 rounded"></div>
          <div class="h-2.5 w-1/2 mt-2 bg-gray-200 dark:bg-gray-500 rounded"></div>
        </li>
      </ul>

      <!-- 空状态 -->
      <div
        v-else-if="!conversations || conversations.length === 0"
        class="flex flex-col items-center justify-center h-full p-6 text-center"
        data-testid="sidebar-empty"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-12 w-12 text-gray-300 dark:text-gray-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>
        <p class="mt-3 text-sm text-gray-500 dark:text-gray-400">
          暂无对话，点击新建开始
        </p>
      </div>

      <!-- 会话列表 -->
      <ul v-else class="space-y-1 p-2" data-testid="conversation-list">
        <li
          v-for="conv in conversations"
          :key="conv.id"
          class="group relative rounded-md transition-colors"
          :class="
            isActive(conv.id)
              ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-900 dark:text-blue-100'
              : 'text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
          "
          :data-testid="`conversation-item-${conv.id}`"
        >
          <button
            type="button"
            class="w-full text-left p-3 pr-8 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-md"
            @click="handleSelect(conv.id)"
          >
            <div class="text-sm font-medium truncate" :title="conv.title || '新对话'">
              {{ conv.title || '新对话' }}
            </div>
            <div
              class="text-xs mt-1 truncate"
              :class="
                isActive(conv.id)
                  ? 'text-blue-700 dark:text-blue-300'
                  : 'text-gray-500 dark:text-gray-400'
              "
            >
              {{ formatRelativeTime(conv.last_msg_at || conv.created_at) }}
            </div>
          </button>
          <!-- 删除按钮：hover 时显示 -->
          <button
            v-if="isActive(conv.id) || true"
            type="button"
            class="absolute top-2 right-2 p-1 rounded text-gray-400 dark:text-gray-500 opacity-0 group-hover:opacity-100 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-red-500 transition-opacity"
            :aria-label="`删除对话 ${conv.title || conv.id}`"
            :data-testid="`delete-btn-${conv.id}`"
            @click.stop="handleDeleteClick(conv)"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3"
              />
            </svg>
          </button>
        </li>
      </ul>
    </div>

    <!-- 折叠状态下的提示 -->
    <div v-else class="flex-1 flex flex-col items-center pt-4 space-y-3">
      <button
        type="button"
        class="p-2 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        aria-label="新建对话"
        @click="handleNewConversation"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
      </button>
    </div>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <div
        v-if="confirmDelete"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        data-testid="delete-confirm-modal"
        @click.self="cancelDelete"
      >
        <div
          class="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-sm w-full mx-4 p-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-modal-title"
        >
          <h2
            id="delete-modal-title"
            class="text-lg font-semibold text-gray-900 dark:text-gray-100"
          >
            确定删除此对话？
          </h2>
          <p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
            此操作不可撤销，对话 "{{ confirmDelete.title || '新对话' }}" 将被永久删除。
          </p>
          <div class="mt-6 flex justify-end gap-2">
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-400"
              data-testid="cancel-delete-btn"
              @click="cancelDelete"
            >
              取消
            </button>
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500"
              data-testid="confirm-delete-btn"
              @click="confirmDeleteAction"
            >
              确定
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </aside>
</template>

<script setup>
/**
 * ChatSidebar 组件
 *
 * 历史会话侧边栏组件，提供以下能力：
 * - 折叠/展开切换（默认展开，宽度 260px，折叠后 48px）
 * - 顶部"新建对话"按钮
 * - 会话列表展示（标题 + 相对时间）
 * - 当前激活会话高亮
 * - 点击会话触发 select-conversation 事件
 * - 鼠标 hover 显示删除按钮，点击后弹出确认弹窗
 * - 加载/空状态展示
 * - 暗黑模式自适应
 */
import { ref } from 'vue'

// ===== Props =====
/**
 * 会话列表数据，每项包含：
 *   id: string 会话唯一 ID
 *   title: string 会话标题
 *   created_at: string ISO 格式创建时间
 *   last_msg_at: string ISO 格式最后消息时间（可空）
 */
const props = defineProps({
  conversations: {
    type: Array,
    default: () => [],
  },
  /** 当前激活的会话 ID（高亮匹配项） */
  activeId: {
    type: [String, null],
    default: null,
  },
  /** 是否处于加载状态（true 时显示骨架屏） */
  loading: {
    type: Boolean,
    default: false,
  },
})

// ===== Emits =====
const emit = defineEmits([
  'new-conversation',
  'select-conversation',
  'delete-conversation',
])

// ===== 内部状态 =====
const collapsed = ref(false)
/** 待删除会话对象；非空时显示确认弹窗 */
const confirmDelete = ref(null)

// ===== 方法 =====
/** 切换侧边栏折叠状态 */
const toggleCollapsed = () => {
  collapsed.value = !collapsed.value
}

/** 触发"新建对话"事件 */
const handleNewConversation = () => {
  emit('new-conversation')
}

/**
 * 判断指定会话是否为当前激活会话
 * @param {string} id 会话 ID
 * @returns {boolean} 是否激活
 */
const isActive = (id) => {
  return props.activeId !== null && props.activeId !== undefined && props.activeId === id
}

/** 触发"选择会话"事件 */
const handleSelect = (id) => {
  emit('select-conversation', id)
}

/** 打开删除确认弹窗 */
const handleDeleteClick = (conv) => {
  confirmDelete.value = conv
}

/** 取消删除 */
const cancelDelete = () => {
  confirmDelete.value = null
}

/** 确认删除，触发事件并关闭弹窗 */
const confirmDeleteAction = () => {
  if (confirmDelete.value) {
    emit('delete-conversation', confirmDelete.value.id)
  }
  confirmDelete.value = null
}

/**
 * 将 ISO 时间格式化为相对时间字符串
 * - 1 分钟内：刚刚
 * - 1 小时内：N 分钟前
 * - 24 小时内：N 小时前
 * - 7 天内：N 天前
 * - 超过 7 天：返回 yyyy-MM-dd 形式
 * @param {string} isoTime ISO 格式时间字符串
 * @returns {string} 相对时间字符串
 */
const formatRelativeTime = (isoTime) => {
  if (!isoTime) return ''
  const date = new Date(isoTime)
  if (Number.isNaN(date.getTime())) return ''
  const now = Date.now()
  const diffSec = Math.floor((now - date.getTime()) / 1000)
  if (diffSec < 60) return '刚刚'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} 分钟前`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} 小时前`
  if (diffSec < 604800) return `${Math.floor(diffSec / 86400)} 天前`
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}
</script>

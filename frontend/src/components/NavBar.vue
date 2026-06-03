<!--
  NavBar 组件
  顶部导航栏,提供 logo、路由导航、深色模式切换和新建会话入口.
  遵循 Apple 风格设计: 半透明 + 模糊背景 + 细分割线.
  响应式:
    - 移动端 (<md): 隐藏桌面导航链接, 显示汉堡按钮 (触发下拉菜单)
    - 桌面端 (>=md): 始终显示导航链接, 隐藏汉堡按钮
    - 新建会话按钮在小屏隐藏, 通过汉堡菜单中的 "新建对话" 入口触发
-->
<template>
  <nav
    class="sticky top-0 z-50 h-14 flex items-center justify-between
           px-3 sm:px-4 md:px-6
           bg-white/70 dark:bg-gray-900/70 backdrop-blur-md
           border-b border-gray-200 dark:border-gray-800
           text-gray-900 dark:text-gray-100"
  >
    <!-- 左侧: Logo (点击回到首页) -->
    <router-link
      to="/"
      class="flex items-center gap-2 text-lg font-semibold
             hover:opacity-80 transition-opacity shrink-0"
    >
      <span class="text-xl">📚</span>
      <span class="hidden sm:inline">ZRAG</span>
    </router-link>

    <!-- 中间: 路由导航链接 (桌面端显示) -->
    <div class="hidden md:flex items-center gap-1">
      <router-link
        v-for="link in links"
        :key="link.to"
        :to="link.to"
        class="px-3 py-1.5 rounded-md text-sm font-medium
               text-gray-600 dark:text-gray-400
               hover:bg-gray-100 dark:hover:bg-gray-800
               hover:text-gray-900 dark:hover:text-gray-100
               transition-colors"
        active-class="!bg-gray-100 !dark:bg-gray-800 !text-gray-900 !dark:text-gray-100"
        :exact-active-class="link.exact ? '!bg-gray-100 !dark:bg-gray-800 !text-gray-900 !dark:text-gray-100' : ''"
      >
        {{ link.label }}
      </router-link>
    </div>

    <!-- 右侧: 功能按钮组 -->
    <div class="flex items-center gap-1 sm:gap-2">
      <!-- 桌面端: 新建会话按钮 (始终显示) -->
      <button
        type="button"
        @click="onNewConversation"
        aria-label="新建会话"
        class="hidden md:inline-flex p-2 rounded-md
               text-gray-600 dark:text-gray-400
               hover:bg-gray-100 dark:hover:bg-gray-800
               hover:text-gray-900 dark:hover:text-gray-100
               transition-colors"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20" height="20" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>

      <!-- 深色模式切换按钮 (始终显示) -->
      <button
        type="button"
        @click="toggleDarkMode"
        :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
        class="p-2 rounded-md
               text-gray-600 dark:text-gray-400
               hover:bg-gray-100 dark:hover:bg-gray-800
               hover:text-gray-900 dark:hover:text-gray-100
               transition-colors"
      >
        <!-- 太阳图标: 当前深色模式, 点击切到浅色 -->
        <svg
          v-if="isDark"
          xmlns="http://www.w3.org/2000/svg"
          width="20" height="20" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2" />
          <path d="M12 20v2" />
          <path d="m4.93 4.93 1.41 1.41" />
          <path d="m17.66 17.66 1.41 1.41" />
          <path d="M2 12h2" />
          <path d="M20 12h2" />
          <path d="m6.34 17.66-1.41 1.41" />
          <path d="m19.07 4.93-1.41 1.41" />
        </svg>
        <!-- 月亮图标: 当前浅色模式, 点击切到深色 -->
        <svg
          v-else
          xmlns="http://www.w3.org/2000/svg"
          width="20" height="20" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </button>

      <!-- 侧边栏切换按钮 (移动端, 仅 ChatView 需要) -->
      <button
        v-if="showSidebarToggle"
        type="button"
        @click="emit('toggle-sidebar')"
        aria-label="切换侧边栏"
        class="md:hidden p-2 rounded-md
               text-gray-600 dark:text-gray-400
               hover:bg-gray-100 dark:hover:bg-gray-800
               hover:text-gray-900 dark:hover:text-gray-100
               transition-colors"
        data-testid="hamburger-btn"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20" height="20" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      <!-- 移动端菜单按钮 (触发下拉) -->
      <button
        type="button"
        @click="toggleMobileMenu"
        aria-label="打开菜单"
        :aria-expanded="mobileMenuOpen"
        class="md:hidden p-2 rounded-md
               text-gray-600 dark:text-gray-400
               hover:bg-gray-100 dark:hover:bg-gray-800
               hover:text-gray-900 dark:hover:text-gray-100
               transition-colors"
        data-testid="mobile-menu-btn"
      >
        <svg
          v-if="!mobileMenuOpen"
          xmlns="http://www.w3.org/2000/svg"
          width="20" height="20" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
        <svg
          v-else
          xmlns="http://www.w3.org/2000/svg"
          width="20" height="20" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>

    <!-- 移动端下拉菜单 -->
    <transition
      enter-active-class="transition ease-out duration-150"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition ease-in duration-100"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <div
        v-if="mobileMenuOpen"
        class="md:hidden absolute top-14 inset-x-0
               bg-white dark:bg-gray-900
               border-b border-gray-200 dark:border-gray-800
               shadow-lg"
        data-testid="mobile-menu"
      >
        <div class="px-2 py-2 space-y-1">
          <router-link
            v-for="link in links"
            :key="link.to"
            :to="link.to"
            class="block px-3 py-2 rounded-md text-sm font-medium
                   text-gray-700 dark:text-gray-200
                   hover:bg-gray-100 dark:hover:bg-gray-800
                   transition-colors"
            active-class="bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            :exact-active-class="link.exact ? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100' : ''"
            @click="closeMobileMenu"
          >
            {{ link.label }}
          </router-link>
          <button
            type="button"
            @click="onMobileNewConversation"
            class="md:hidden w-full text-left px-3 py-2 rounded-md text-sm font-medium
                   text-gray-700 dark:text-gray-200
                   hover:bg-gray-100 dark:hover:bg-gray-800
                   transition-colors"
            data-testid="mobile-new-conversation-btn"
          >
            新建对话
          </button>
        </div>
      </div>
    </transition>
  </nav>
</template>

<script setup>
/**
 * NavBar 组件
 *
 * 顶部导航栏组件, 负责:
 * - 渲染 Logo 与桌面端路由导航链接
 * - 切换深色模式 (写入 localStorage, 同步 <html> class)
 * - 触发 "新建会话" 事件, 由父组件 (App.vue) 实际处理
 * - 移动端下拉菜单 (含点击外部关闭)
 * - 可选的侧边栏切换按钮 (供 ChatView 在 <md 屏幕下使用)
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'

/** localStorage 中用于持久化暗黑模式偏好的 key */
const DARK_MODE_STORAGE_KEY = 'darkMode'
/** 用于定位"移动端下拉菜单"与触发按钮的 data-testid */
const MOBILE_MENU_TESTID = 'mobile-menu'
const MOBILE_MENU_BTN_TESTID = 'mobile-menu-btn'

const emit = defineEmits([
  'new-conversation',
  'toggle-sidebar',
])

/**
 * 组件 Props
 *
 * @typedef {Object} NavBarProps
 * @property {boolean} [showSidebarToggle=false] - 是否显示"侧边栏切换"按钮 (汉堡菜单);
 *   一般由 ChatView 传入 true, 在 <md 屏幕下用于弹出/隐藏 ChatSidebar
 */
defineProps({
  showSidebarToggle: {
    type: Boolean,
    default: false,
  },
})

/**
 * 当前深色模式开关
 * 初始从 document.documentElement 的 'dark' class 读取,
 * 保持与 main.js 初始化逻辑一致.
 */
const isDark = ref(false)

/** 移动端下拉菜单开关 */
const mobileMenuOpen = ref(false)

/** 路由导航链接配置 */
const links = [
  { to: '/', label: '对话', exact: true },
  { to: '/sources', label: '知识库', exact: false },
]

/**
 * 组件挂载时同步当前深色模式状态
 * 避免在 main.js 初始化完成前出现 UI 与实际状态不一致.
 */
onMounted(() => {
  isDark.value = document.documentElement.classList.contains('dark')
  document.addEventListener('click', onDocumentClick)
})

/**
 * 组件卸载时移除全局点击监听, 防止内存泄漏.
 */
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})

/**
 * 切换深色模式
 * 1. toggle document.documentElement 的 'dark' class
 * 2. 将最新状态写入 localStorage('darkMode')
 * 3. 同步更新当前组件的 isDark 引用以刷新图标
 *
 * @returns {void}
 */
function toggleDarkMode() {
  const root = document.documentElement
  const next = !root.classList.contains('dark')
  root.classList.toggle('dark', next)
  localStorage.setItem(DARK_MODE_STORAGE_KEY, String(next))
  isDark.value = next
}

/**
 * 触发"新建会话"事件
 * 实际行为由父组件 (App.vue) 监听并实现,
 * NavBar 自身只负责发出意图, 保持组件职责单一.
 *
 * @returns {void}
 */
function onNewConversation() {
  emit('new-conversation')
}

/**
 * 切换移动端下拉菜单
 *
 * @returns {void}
 */
function toggleMobileMenu() {
  mobileMenuOpen.value = !mobileMenuOpen.value
}

/**
 * 关闭移动端下拉菜单
 *
 * @returns {void}
 */
function closeMobileMenu() {
  mobileMenuOpen.value = false
}

/**
 * 移动端"新建对话"按钮: 先关闭菜单再 emit, 避免菜单未关闭导致 UI 闪烁.
 *
 * @returns {void}
 */
function onMobileNewConversation() {
  closeMobileMenu()
  emit('new-conversation')
}

/**
 * 判断事件源是否落在指定容器内
 *
 * @param {EventTarget|null} target - 事件源
 * @param {Element|null} container - 容器元素
 * @returns {boolean} 是否在容器内
 */
function isInside(target, container) {
  if (!container) return false
  return target instanceof Node && container.contains(target)
}

/**
 * 文档级点击事件: 点击菜单外部时关闭菜单
 *
 * @param {MouseEvent} event - 鼠标事件
 * @returns {void}
 */
function onDocumentClick(event) {
  if (!mobileMenuOpen.value) return
  const menu = document.querySelector(`[data-testid="${MOBILE_MENU_TESTID}"]`)
  const btn = document.querySelector(`[data-testid="${MOBILE_MENU_BTN_TESTID}"]`)
  // 菜单/按钮内的点击不处理
  const inMenu = isInside(event.target, menu)
  const inBtn = isInside(event.target, btn)
  if (!inMenu && !inBtn) {
    mobileMenuOpen.value = false
  }
}
</script>

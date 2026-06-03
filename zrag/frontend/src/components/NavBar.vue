<!--
  NavBar 组件
  顶部导航栏,提供 logo、路由导航、深色模式切换和新建会话入口.
  遵循 Apple 风格设计: 半透明 + 模糊背景 + 细分割线.
-->
<template>
  <nav
    class="sticky top-0 z-50 h-14 flex items-center justify-between px-6
           bg-white/70 dark:bg-gray-900/70 backdrop-blur-md
           border-b border-gray-200 dark:border-gray-800
           text-gray-900 dark:text-gray-100"
  >
    <!-- 左侧: Logo (点击回到首页) -->
    <router-link
      to="/"
      class="flex items-center gap-2 text-lg font-semibold
             hover:opacity-80 transition-opacity"
    >
      <span class="text-xl">📚</span>
      <span>ZRAG</span>
    </router-link>

    <!-- 中间: 路由导航链接 -->
    <div class="flex items-center gap-1">
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
    <div class="flex items-center gap-2">
      <!-- 深色模式切换按钮 -->
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

      <!-- 新建会话按钮 -->
      <button
        type="button"
        @click="onNewConversation"
        aria-label="新建会话"
        class="p-2 rounded-md
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
    </div>
  </nav>
</template>

<script setup>
import { ref, onMounted } from 'vue'

// ======================
// Emits 定义
// ======================
const emit = defineEmits(['new-conversation'])

// ======================
// 响应式状态
// ======================

/**
 * 当前深色模式开关
 * 初始从 document.documentElement 的 'dark' class 读取,
 * 保持与 main.js 初始化逻辑一致.
 */
const isDark = ref(false)

// 路由导航链接配置
const links = [
  { to: '/', label: '对话', exact: true },
  { to: '/sources', label: '知识库', exact: false },
]

// ======================
// 生命周期
// ======================

/**
 * 组件挂载时同步当前深色模式状态
 * 避免在 main.js 初始化完成前出现 UI 与实际状态不一致.
 */
onMounted(() => {
  isDark.value = document.documentElement.classList.contains('dark')
})

// ======================
// 方法定义
// ======================

/**
 * 切换深色模式
 * 1. toggle document.documentElement 的 'dark' class
 * 2. 将最新状态写入 localStorage('darkMode')
 * 3. 同步更新当前组件的 isDark 引用以刷新图标
 */
function toggleDarkMode() {
  const root = document.documentElement
  const next = !root.classList.contains('dark')
  root.classList.toggle('dark', next)
  localStorage.setItem('darkMode', String(next))
  isDark.value = next
}

/**
 * 触发"新建会话"事件
 * 实际行为由父组件 (App.vue) 监听并实现,
 * NavBar 自身只负责发出意图, 保持组件职责单一.
 */
function onNewConversation() {
  emit('new-conversation')
}
</script>

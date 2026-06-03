<!--
  NotFoundView.vue
  全局 404 页面,占位兜底,大号渐变 404 + 返回首页按钮.
-->
<template>
  <div class="min-h-screen flex items-center justify-center px-4">
    <div class="text-center">
      <h1
        class="text-9xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 select-none"
      >
        404
      </h1>
      <p class="mt-4 text-2xl text-gray-500 dark:text-gray-400">页面未找到</p>
      <p class="mt-2 text-sm text-gray-400 dark:text-gray-500">
        您访问的页面不存在或已被移除
      </p>
      <button
        type="button"
        class="mt-8 px-6 py-2.5 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-full transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
        @click="goHome"
      >
        返回首页
      </button>
    </div>
  </div>
</template>

<script setup>
/**
 * 404 视图组件
 *
 * 全局 404 占位页, 点击"返回首页"按钮使用 router.push('/')
 * 跳转至根路径 (ChatView).
 */
import { useRouter } from 'vue-router'

const router = useRouter()

/**
 * 跳转回首页 (根路径)
 *
 * @returns {void}
 */
function goHome() {
  router.push('/')
}
</script>

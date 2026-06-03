<!--
  ToastContainer.vue
  全局 Toast 容器组件,通过 useToast() 共享 toasts 数组,
  在右上角渲染当前所有通知,支持自动消失与手动关闭.
-->
<template>
  <div
    class="fixed top-4 right-4 flex flex-col gap-2 pointer-events-none"
    style="z-index: 9999"
    aria-live="polite"
    aria-atomic="true"
  >
    <transition-group name="toast" tag="div" class="flex flex-col gap-2">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="pointer-events-auto min-w-[280px] max-w-sm px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 text-white transition-all"
        :class="bgClass(t.type)"
        role="status"
      >
        <span class="text-lg leading-none" aria-hidden="true">
          <template v-if="t.type === 'success'">&#10003;</template>
          <template v-else-if="t.type === 'error'">&#10007;</template>
          <template v-else>&#8505;</template>
        </span>
        <span class="flex-1 text-sm leading-snug break-words">{{ t.message }}</span>
        <button
          type="button"
          class="text-white/80 hover:text-white transition-colors text-lg leading-none"
          aria-label="关闭通知"
          @click="dismiss(t.id)"
        >
          &times;
        </button>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
/**
 * Toast 容器组件
 *
 * 从 useToast() 读取全局 toasts 列表并渲染.
 * 点击右侧 X 按钮可手动关闭单条 Toast.
 */
import { useToast } from '../composables/useToast.js'

const { toasts, dismiss } = useToast()

/**
 * 根据通知类型返回 Tailwind 背景色类.
 *
 * @param {string} type - 'success' | 'error' | 'info'
 * @returns {string} 背景色类名
 */
function bgClass(type) {
  if (type === 'success') return 'bg-green-500 dark:bg-green-600'
  if (type === 'error') return 'bg-red-500 dark:bg-red-600'
  return 'bg-blue-500 dark:bg-blue-600'
}
</script>

<style scoped>
/* 从右侧滑入并淡入的进入/退出动画 */
.toast-enter-active,
.toast-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>

<template>
  <div class="min-h-screen bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <router-view />
    <ToastContainer />
  </div>
</template>

<script setup>
/**
 * 根组件
 *
 * 渲染当前路由对应的视图,并在全局挂载 Toast 容器,
 * 保证任意视图内的 useToast() 调用都能即时显示在右上角.
 */
import ToastContainer from './components/ToastContainer.vue'
</script>

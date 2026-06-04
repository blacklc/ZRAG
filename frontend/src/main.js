/**
 * 应用入口
 *
 * 负责:
 * 1. 初始化暗黑模式 (localStorage 优先, 其次回退到系统偏好)
 * 2. 创建并注册 Vue Router
 * 3. 挂载根组件到 #app 节点
 */

import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import ChatView from './views/ChatView.vue'
import SourcesView from './views/SourcesView.vue'
import NotFoundView from './views/NotFoundView.vue'
import './style.css'

/** localStorage 中用于持久化暗黑模式偏好的 key */
const DARK_MODE_STORAGE_KEY = 'darkMode'
/** Tailwind 'md' 断点 (像素), 与 NavBar 保持一致 */
const MD_BREAKPOINT_PX = 768

/**
 * 判断当前是否应启用暗黑模式
 *
 * 优先级: localStorage('darkMode' === 'true') > 系统偏好 > 浅色.
 *
 * @returns {boolean} 是否启用暗黑模式
 */
function shouldEnableDarkMode() {
  const stored = localStorage.getItem(DARK_MODE_STORAGE_KEY)
  if (stored === 'true') return true
  if (stored === 'false') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

/**
 * 应用启动前的暗黑模式初始化
 *
 * 在挂载 Vue 应用前同步给 <html> 加上 'dark' class,
 * 避免首屏出现 "浅色 -> 暗黑" 的闪烁 (FOUC).
 */
function initDarkMode() {
  if (shouldEnableDarkMode()) {
    document.documentElement.classList.add('dark')
  }
}

initDarkMode()

const router = createRouter({
  history: createWebHistory('/zrag/'),
  routes: [
    { path: '/', component: ChatView },
    { path: '/sources', component: SourcesView },
    { path: '/:pathMatch(.*)*', component: NotFoundView },
  ],
})

createApp(App).use(router).mount('#app')

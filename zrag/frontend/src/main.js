import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import ChatView from './views/ChatView.vue'
import SourcesView from './views/SourcesView.vue'
import NotFoundView from './views/NotFoundView.vue'
import './style.css'

// 暗黑模式初始化
const darkMode = localStorage.getItem('darkMode')
if (darkMode === 'true' || (darkMode === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
  document.documentElement.classList.add('dark')
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: ChatView },
    { path: '/sources', component: SourcesView },
    { path: '/:pathMatch(.*)*', component: NotFoundView },
  ],
})

createApp(App).use(router).mount('#app')

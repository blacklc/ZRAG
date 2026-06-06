/**
 * Vue Router 配置
 *
 * 路由集中在此模块以便测试和扩展。
 * 历史模式使用 createWebHistory('/zrag/') 与 nginx try_files 配合。
 */

import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import SourcesView from '../views/SourcesView.vue'
import NotFoundView from '../views/NotFoundView.vue'

const router = createRouter({
  history: createWebHistory('/zrag/'),
  routes: [
    { path: '/', component: ChatView },
    { path: '/sources', component: SourcesView },
    { path: '/:pathMatch(.*)*', component: NotFoundView },
  ],
})

export default router

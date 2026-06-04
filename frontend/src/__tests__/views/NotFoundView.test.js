/**
 * NotFoundView.vue 页面测试
 *
 * 验证 404 页面的渲染与导航行为:
 * - 显示 "404" 文字
 * - 存在 "返回首页" 按钮
 * - 点击按钮后调用 router.push('/')
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import NotFoundView from '../../views/NotFoundView.vue'

describe('NotFoundView.vue', () => {
  /** @type {import('vue-router').Router} */
  let router

  beforeEach(async () => {
    router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/', component: { template: '<div>Home</div>' } },
      ],
    })
    // 模拟路由进入到一个不存在的路径
    await router.push('/non-existent')
  })

  it('应渲染 "404" 文字', () => {
    const wrapper = mount(NotFoundView, {
      global: { plugins: [router] },
    })

    expect(wrapper.text()).toContain('404')
  })

  it('应存在 "返回首页" 按钮', () => {
    const wrapper = mount(NotFoundView, {
      global: { plugins: [router] },
    })

    const btn = wrapper.find('button')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toBe('返回首页')
  })

  it('点击 "返回首页" 按钮后应调用 router.push("/")', async () => {
    const pushSpy = vi.spyOn(router, 'push')
    const wrapper = mount(NotFoundView, {
      global: { plugins: [router] },
    })

    const btn = wrapper.find('button')
    await btn.trigger('click')

    expect(pushSpy).toHaveBeenCalledTimes(1)
    expect(pushSpy).toHaveBeenCalledWith('/')
  })
})

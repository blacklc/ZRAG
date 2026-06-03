<!--
  SourcesView 页面
  知识库来源管理页面,提供以下能力:
  - 顶部标题区与"增量摄入"/"全量摄入"两个操作按钮
  - 来源卡片网格,展示 source_type, doc_count, last_imported
  - 摄入过程中显示 indeterminate 进度条 (animate-pulse)
  - 摄入完成 / 失败时显示 Toast 通知
  - 加载状态显示骨架屏
  - 空状态提示用户点击上方按钮开始摄入
  - 顶部引用 NavBar 组件
  - 暗黑模式自适应
-->
<template>
  <div class="min-h-screen flex flex-col bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <!-- 顶部导航栏 -->
    <NavBar />

    <!-- 主体内容区 -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-8">
      <!-- 顶部标题 + 操作按钮 -->
      <header class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div class="min-w-0">
          <h1 class="text-xl sm:text-2xl font-bold tracking-tight">知识库来源</h1>
          <p class="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            管理 RAG 系统的文档来源,执行增量或全量摄入
          </p>
        </div>
        <div class="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 shrink-0">
          <button
            type="button"
            :disabled="ingesting"
            class="inline-flex items-center justify-center gap-1.5 px-3 sm:px-4 py-2 text-sm font-medium
                   text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800
                   border border-gray-300 dark:border-gray-600
                   hover:bg-gray-50 dark:hover:bg-gray-700
                   rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-colors"
            data-testid="incremental-ingest-btn"
            @click="handleIngest(false)"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            增量摄入
          </button>
          <button
            type="button"
            :disabled="ingesting"
            class="inline-flex items-center justify-center gap-1.5 px-3 sm:px-4 py-2 text-sm font-medium
                   text-white bg-blue-600 hover:bg-blue-700
                   rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-colors"
            data-testid="full-ingest-btn"
            @click="handleIngest(true)"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            全量摄入
          </button>
        </div>
      </header>

      <!-- 摄入进度条 (indeterminate) -->
      <div
        v-if="ingesting"
        class="mb-6 h-1.5 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden"
        data-testid="ingest-progress"
        role="progressbar"
        aria-label="摄入进行中"
      >
        <div class="h-full w-1/3 bg-blue-600 dark:bg-blue-500 animate-pulse rounded-full"></div>
      </div>

      <!-- 加载状态: 骨架屏 -->
      <div
        v-if="loading"
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4"
        data-testid="sources-skeleton"
      >
        <div
          v-for="i in 6"
          :key="i"
          class="p-5 rounded-lg border border-gray-200 dark:border-gray-700
                 bg-white dark:bg-gray-800 animate-pulse"
        >
          <div class="h-5 w-1/3 bg-gray-300 dark:bg-gray-600 rounded"></div>
          <div class="h-4 w-1/2 mt-3 bg-gray-200 dark:bg-gray-500 rounded"></div>
          <div class="h-3 w-1/4 mt-4 bg-gray-200 dark:bg-gray-500 rounded"></div>
        </div>
      </div>

      <!-- 空状态 -->
      <div
        v-else-if="!sources || sources.length === 0"
        class="flex flex-col items-center justify-center py-20 text-center"
        data-testid="sources-empty"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-16 w-16 text-gray-300 dark:text-gray-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
          />
        </svg>
        <p class="mt-4 text-base text-gray-500 dark:text-gray-400">
          暂无来源,点击上方按钮开始摄入
        </p>
      </div>

      <!-- 来源卡片网格 -->
      <div
        v-else
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4"
        data-testid="sources-grid"
      >
        <article
          v-for="source in sources"
          :key="source.source_type"
          class="p-4 sm:p-5 rounded-lg border border-gray-200 dark:border-gray-700
                 bg-white dark:bg-gray-800
                 hover:border-blue-400 dark:hover:border-blue-500
                 hover:shadow-sm transition-all"
          :data-testid="`source-card-${source.source_type}`"
        >
          <!-- 头部: 类型 + 文档数 -->
          <div class="flex items-start justify-between gap-2">
            <h3 class="text-base font-semibold truncate" :title="source.source_type">
              {{ source.source_type }}
            </h3>
            <span
              class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
                     bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200
                     shrink-0"
            >
              {{ source.doc_count }} 文档
            </span>
          </div>

          <!-- 中部: 文档统计 -->
          <div class="mt-4 flex items-baseline gap-1">
            <span class="text-2xl font-bold">{{ source.doc_count }}</span>
            <span class="text-sm text-gray-500 dark:text-gray-400">份文档</span>
          </div>

          <!-- 底部: 最后摄入时间 -->
          <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
            <p class="text-xs text-gray-500 dark:text-gray-400">
              最后摄入: {{ formatRelativeTime(source.last_imported) || '—' }}
            </p>
          </div>
        </article>
      </div>
    </main>

    <!-- Toast 通知 -->
    <Teleport to="body">
      <transition
        enter-active-class="transition ease-out duration-200"
        enter-from-class="opacity-0 translate-y-2"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition ease-in duration-150"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 translate-y-2"
      >
        <div
          v-if="toast.show"
          class="fixed bottom-6 right-6 z-50 max-w-sm w-full sm:w-auto
                 rounded-lg shadow-lg overflow-hidden"
          :class="
            toast.type === 'success'
              ? 'bg-green-50 dark:bg-green-900/40 border border-green-200 dark:border-green-800'
              : 'bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800'
          "
          data-testid="toast"
          role="alert"
        >
          <div class="flex items-start gap-3 p-4">
            <!-- 成功图标 -->
            <svg
              v-if="toast.type === 'success'"
              xmlns="http://www.w3.org/2000/svg"
              class="h-5 w-5 text-green-500 shrink-0 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <!-- 失败图标 -->
            <svg
              v-else
              xmlns="http://www.w3.org/2000/svg"
              class="h-5 w-5 text-red-500 shrink-0 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div class="flex-1 min-w-0">
              <p
                class="text-sm font-medium"
                :class="
                  toast.type === 'success'
                    ? 'text-green-800 dark:text-green-200'
                    : 'text-red-800 dark:text-red-200'
                "
              >
                {{ toast.message }}
              </p>
              <!-- 报告详情 -->
              <div
                v-if="lastReport"
                class="mt-2 text-xs"
                :class="
                  toast.type === 'success'
                    ? 'text-green-700 dark:text-green-300'
                    : 'text-red-700 dark:text-red-300'
                "
              >
                <span>处理 {{ lastReport.processed || 0 }}</span>
                <span v-if="lastReport.added" class="ml-2">新增 {{ lastReport.added }}</span>
                <span v-if="lastReport.skipped" class="ml-2">跳过 {{ lastReport.skipped }}</span>
                <span v-if="lastReport.failed" class="ml-2">失败 {{ lastReport.failed }}</span>
              </div>
            </div>
            <button
              type="button"
              class="shrink-0 -mr-1 -mt-1 p-1 rounded-md
                     text-gray-400 hover:text-gray-600 dark:hover:text-gray-200
                     focus:outline-none focus:ring-2 focus:ring-gray-400"
              aria-label="关闭通知"
              @click="dismissToast"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<script setup>
/**
 * SourcesView 页面
 *
 * 知识库来源管理页面, 提供以下能力:
 * - 进入页面时调用 listSources() 加载来源列表
 * - 顶部"增量摄入"/"全量摄入"按钮触发 ingestDocuments() 接口
 * - 摄入过程中显示 indeterminate 进度条
 * - 摄入完成后重新拉取列表并显示报告 Toast
 * - 摄入失败时显示错误 Toast
 * - 加载状态显示骨架屏
 * - 空状态显示引导文案
 * - 顶部嵌入 NavBar 组件, 支持暗黑模式
 */
import { ref, onMounted } from 'vue'
import NavBar from '../components/NavBar.vue'
import { listSources, ingestDocuments } from '../api/endpoints.js'

/** Toast 自动消失默认时长 (毫秒) */
const DEFAULT_TOAST_DURATION_MS = 3000
/** 时间区间阈值 (秒), 用于相对时间格式化 */
const RELATIVE_TIME_THRESHOLDS = Object.freeze({
  MINUTE: 60,
  HOUR: 3600,
  DAY: 86400,
  WEEK: 604800,
})

/** 来源列表数据, 每项包含 source_type, doc_count, last_imported */
const sources = ref([])
/** 列表加载状态, true 时显示骨架屏 */
const loading = ref(false)
/** 摄入操作进行中状态, true 时显示进度条与禁用按钮 */
const ingesting = ref(false)
/** 最近一次摄入报告, 用于在 Toast 中展示处理/新增/跳过/失败数 */
const lastReport = ref(null)
/**
 * 简单 Toast 状态
 * - show: 是否显示
 * - type: 'success' | 'error'
 * - message: 提示文案
 */
const toast = ref({ show: false, type: 'success', message: '' })
/** Toast 自动消失定时器 ID, 用于手动关闭时清理 */
let toastTimer = null

/**
 * 清除 Toast 自动消失定时器
 *
 * @returns {void}
 */
function clearToastTimer() {
  if (toastTimer) {
    clearTimeout(toastTimer)
    toastTimer = null
  }
}

/**
 * 显示 Toast 通知
 *
 * @param {string} type - 通知类型: 'success' | 'error'
 * @param {string} message - 通知文案
 * @param {number} [duration=3000] - 自动消失时长 (毫秒)
 * @returns {void}
 */
function showToast(type, message, duration = DEFAULT_TOAST_DURATION_MS) {
  clearToastTimer()
  toast.value = { show: true, type, message }
  toastTimer = setTimeout(() => {
    toast.value.show = false
    toastTimer = null
  }, duration)
}

/** 手动关闭 Toast, 清理定时器 */
function dismissToast() {
  clearToastTimer()
  toast.value.show = false
}

/**
 * 将后端返回的来源数据规范为数组
 * - 直接是数组: 原样返回
 * - 包含 items 字段: 返回 items
 * - 其它: 返回空数组
 *
 * @param {*} data - 后端响应
 * @returns {Array} 规范化的来源列表
 */
function normalizeSources(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.items)) return data.items
  return []
}

/**
 * 加载来源列表
 * - 设置 loading 标志以触发骨架屏
 * - 异常时显示错误 Toast, 并保留现有列表数据
 *
 * @returns {Promise<void>}
 */
async function loadSources() {
  loading.value = true
  try {
    sources.value = normalizeSources(await listSources())
  } catch (err) {
    showToast('error', `加载来源列表失败: ${err.message || '未知错误'}`)
  } finally {
    loading.value = false
  }
}

/**
 * 触发摄入操作
 * 1. 设置 ingesting 标志显示进度条
 * 2. 调用 ingestDocuments 接口 (source_type: null 表示全部来源)
 * 3. 完成后重新拉取列表并展示报告
 * 4. 失败时显示错误 Toast
 *
 * @param {boolean} full - 是否全量摄入
 * @returns {Promise<void>}
 */
async function handleIngest(full) {
  if (ingesting.value) return
  ingesting.value = true
  lastReport.value = null
  const actionLabel = full ? '全量摄入' : '增量摄入'
  try {
    const report = await ingestDocuments({ source_type: null, full })
    lastReport.value = report || {}
    showToast('success', `${actionLabel}完成`)
    // 摄入成功后重新拉取来源列表
    await loadSources()
  } catch (err) {
    showToast('error', `${actionLabel}失败: ${err.message || '未知错误'}`)
  } finally {
    ingesting.value = false
  }
}

/**
 * 将相对时间值格式化为人类可读字符串
 *
 * @param {number} diffSec - 与当前时间的差值 (秒)
 * @param {Date} date - 原始 Date 对象
 * @returns {string} 相对时间字符串
 */
function formatRelativeDiff(diffSec, date) {
  const { MINUTE, HOUR, DAY, WEEK } = RELATIVE_TIME_THRESHOLDS
  if (diffSec < MINUTE) return '刚刚'
  if (diffSec < HOUR) return `${Math.floor(diffSec / MINUTE)} 分钟前`
  if (diffSec < DAY) return `${Math.floor(diffSec / HOUR)} 小时前`
  if (diffSec < WEEK) return `${Math.floor(diffSec / DAY)} 天前`
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * 将 ISO 时间格式化为相对时间字符串
 * - 1 分钟内: 刚刚
 * - 1 小时内: N 分钟前
 * - 24 小时内: N 小时前
 * - 7 天内: N 天前
 * - 超过 7 天: 返回 yyyy-MM-dd 形式
 * - 空值或非法值: 返回空串
 *
 * @param {string} isoTime - ISO 格式时间字符串
 * @returns {string} 相对时间字符串
 */
function formatRelativeTime(isoTime) {
  if (!isoTime) return ''
  const date = new Date(isoTime)
  if (Number.isNaN(date.getTime())) return ''
  const diffSec = Math.floor((Date.now() - date.getTime()) / 1000)
  return formatRelativeDiff(diffSec, date)
}

/** 组件挂载时加载来源列表 */
onMounted(() => {
  loadSources()
})
</script>

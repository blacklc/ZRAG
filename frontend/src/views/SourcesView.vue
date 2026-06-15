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
          <!-- 数据源选择器 -->
          <select
            v-model="selectedSource"
            :disabled="ingesting"
            class="inline-flex items-center px-3 py-2 text-sm border border-gray-300 dark:border-gray-600
                   rounded-md bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200
                   focus:outline-none focus:ring-2 focus:ring-blue-500"
            data-testid="source-selector"
          >
            <option value="" disabled>选择数据源</option>
            <option v-for="s in availableSources" :key="s" :value="s">{{ s }}</option>
          </select>
          <button
            type="button"
            :disabled="ingesting || !selectedSource"
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
            :disabled="ingesting || !selectedSource"
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

      <!-- 导出提示区 (macOS Notes 专用) -->
      <div
        v-if="showExportHint && taskId"
        class="mb-6 p-4 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20"
        data-testid="export-hint"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="flex-1">
            <p class="text-sm font-medium text-amber-800 dark:text-amber-200">
              ⚠️ 请在终端执行以下命令导出笔记
            </p>
            <pre class="mt-2 p-2 rounded bg-amber-100 dark:bg-amber-900/40 text-sm text-amber-900 dark:text-amber-100 overflow-x-auto">python3 export_notes.py {{ taskId }}</pre>
          </div>
          <button
            type="button"
            class="shrink-0 p-1.5 rounded text-amber-600 hover:text-amber-800 hover:bg-amber-100 dark:hover:bg-amber-800/50 transition-colors"
            title="复制命令"
            @click="copyCommand"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>
      </div>

      <!-- 进度区 -->
      <div
        v-if="ingesting"
        class="mb-6 p-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
        data-testid="ingest-progress"
      >
        <div class="mb-2">
          <span v-if="taskId" class="text-xs text-gray-400 dark:text-gray-500 block mb-1">
            任务: {{ taskId }}
          </span>
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
              {{ statusText }}
            </span>
          <button
            type="button"
            :disabled="cancelLoading"
            class="text-xs font-medium text-red-600 hover:text-red-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            @click="handleCancel"
          >
            {{ cancelLoading ? '取消中...' : '取消' }}
          </button>
          </div>
        </div>
        <div class="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <!-- 确定进度条：根据 processed/total 显示百分比 -->
          <div
            v-if="isDeterminate"
            class="h-full rounded-full bg-blue-600 transition-all duration-500 ease-out"
            :style="{ width: (processed / total * 100) + '%' }"
          ></div>
          <!-- 不确定进度条：pending / waiting / processing 但 total 为 0 时显示 -->
          <div
            v-else-if="isIndeterminate"
            class="progress-bar-indeterminate"
          ></div>
        </div>
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
import { ref, watch, onMounted, onUnmounted } from 'vue'
import NavBar from '../components/NavBar.vue'
import { listSources } from '../api/endpoints.js'
import { getUserMessage } from '../api/index.js'
import { useToast } from '../composables/useToast.js'
import { useIngest } from '../composables/useIngest.js'
import { useAvailableSources } from '../composables/useAvailableSources.js'
import { formatRelativeTime } from '../utils/time.js'

const toast = useToast()
const {
  taskId, taskStatus, total, processed,
  ingesting, cancelLoading,
  statusText, isIndeterminate, isDeterminate,
  startIngest, cancelTask, restoreActiveTask,
  dispose,
} = useIngest()
const { availableSources, loadAvailableSources } = useAvailableSources()
/** 导出提示显隐控制（macOS Notes 专用） */
const showExportHint = ref(false)

/** 来源列表数据, 每项包含 source_type, doc_count, last_imported */
const sources = ref([])
/** 列表加载状态, true 时显示骨架屏 */
const loading = ref(false)
/** 选中的数据源 */
const selectedSource = ref('')


/**
 * 将后端返回的来源数据规范为数组
 *
 * @param {*} data - 后端响应
 * @returns {Array} 规范化的来源列表
 */
function normalizeSources(data) {
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.sources)) return data.sources
  return []
}

/**
 * 加载来源列表
 *
 * @returns {Promise<void>}
 */
async function loadSources() {
  loading.value = true
  try {
    sources.value = normalizeSources(await listSources())
  } catch (err) {
    toast.error(`加载来源列表失败: ${getUserMessage(err)}`)
  } finally {
    loading.value = false
  }
}

/**
 * 触发摄入操作
 *
 * @param {boolean} full - 是否全量摄入
 * @returns {Promise<void>}
 */
async function handleIngest(full) {
  if (!selectedSource.value || ingesting.value) return
  const actionLabel = full ? '全量摄入' : '增量摄入'
  try {
    await startIngest(selectedSource.value, full)
    showExportHint.value = true
  } catch (err) {
    toast.error(`${actionLabel}失败: ${getUserMessage(err)}`)
  }
}

/** 取消任务 */
async function handleCancel() {
  try {
    await cancelTask()
  } catch {
    toast.error('取消失败，请重试')
  }
}

/** 复制导出命令 */
async function copyCommand() {
  try {
    await navigator.clipboard.writeText(`python3 export_notes.py ${taskId.value}`)
    toast.success('命令已复制')
  } catch {
    toast.error('复制失败')
  }
}

// 监听任务状态变化
watch(taskStatus, (status) => {
  if (['done', 'cancelled', 'failed'].includes(status)) {
    showExportHint.value = false
  }
  if (status === 'done') {
    toast.success(total.value > 0 ? `摄入完成，共处理 ${total.value} 篇` : '摄入完成')
    loadSources()
  } else if (status === 'cancelled') {
    toast.success('摄入已取消')
  } else if (status === 'failed') {
    toast.error('摄入异常终止')
  }
})

onMounted(() => {
  loadSources()
  loadAvailableSources()
  restoreActiveTask()
})

onUnmounted(() => {
  dispose()
})
</script>

<style scoped>
/**
 * 不确定进度条动画
 *
 * 用于 pending / waiting / processing 但 total 为 0 时的进度显示。
 * 使用蓝白渐变背景从左到右连续移动，表示任务正在进行中。
 */
@keyframes progress-indeterminate {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.progress-bar-indeterminate {
  height: 100%;
  background: linear-gradient(90deg, transparent, #3b82f6, transparent);
  animation: progress-indeterminate 1.5s ease-in-out infinite;
}
</style>

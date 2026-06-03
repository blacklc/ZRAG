<!--
  ChatMessage 组件
  单条消息气泡,支持:
  - role=user/assistant 双样式对齐
  - Markdown 渲染 (marked + DOMPurify 防 XSS)
  - 代码块语法高亮 (highlight.js, github / github-dark 跟随系统主题)
  - 来源标注 (assistant 消息下方)
  - 复制按钮 (hover 显示, 点击复制原文, "已复制" 提示 2 秒)
  - 时间戳 (灰色小字, 右下角)
  - 暗黑模式自适应
-->
<template>
  <div
    class="group flex w-full"
    :class="isUser ? 'justify-end' : 'justify-start'"
    :data-testid="`message-${message.id}`"
    :data-role="message.role"
  >
    <div
      class="relative max-w-[90%] sm:max-w-2xl md:max-w-3xl px-3 py-2.5 sm:px-4 sm:py-3 rounded-lg shadow-sm"
      :class="bubbleClass"
    >
      <!-- Markdown 渲染区域 -->
      <div
        v-if="renderedHtml"
        class="markdown-body text-sm leading-relaxed break-words"
        v-html="renderedHtml"
      ></div>
      <!-- 纯文本兜底: 当 content 为空或渲染失败时显示 -->
      <div v-else class="text-sm leading-relaxed whitespace-pre-wrap break-words">
        {{ message.content }}
      </div>

      <!-- 来源标注: 仅 assistant 消息显示 -->
      <div
        v-if="!isUser && hasSources"
        class="mt-3 pt-2 border-t border-gray-200/60 dark:border-gray-600/60"
        data-testid="message-sources"
      >
        <div class="text-xs text-gray-500 dark:text-gray-400">
          <span class="mr-1">📎</span>
          <span>来源:</span>
          <span
            v-for="(src, idx) in message.sources"
            :key="src.source_id || idx"
            class="ml-1"
          >
            <span
              class="inline-block max-w-xs truncate align-bottom"
              :title="src.doc_title"
            >
              {{ src.doc_title }}
            </span>
            <span v-if="idx < message.sources.length - 1" class="mr-1">,</span>
          </span>
        </div>
      </div>

      <!-- 底部栏: 复制按钮 + 时间戳 -->
      <div
        class="mt-1.5 flex items-center justify-end gap-2 text-xs"
        :class="isUser ? 'text-blue-100/80' : 'text-gray-400 dark:text-gray-500'"
      >
        <!-- 复制按钮: hover 时显示, 已复制时显示 "已复制" -->
        <button
          type="button"
          class="px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100
                 hover:bg-black/10 dark:hover:bg-white/10
                 focus:opacity-100 focus:outline-none focus:ring-1 focus:ring-blue-500
                 transition-opacity"
          :class="copyState === 'copied' ? 'opacity-100' : ''"
          :aria-label="copyState === 'copied' ? '已复制' : '复制消息内容'"
          data-testid="copy-btn"
          @click="handleCopy"
        >
          <span v-if="copyState === 'copied'" class="text-green-300">已复制</span>
          <span v-else>复制</span>
        </button>
        <!-- 时间戳 -->
        <span :data-testid="`timestamp-${message.id}`">
          {{ formattedTime }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * ChatMessage 组件
 *
 * 单条消息气泡, 提供以下能力:
 * - 区分 user / assistant 两种气泡样式与对齐方式
 * - Markdown 内容渲染 (marked 解析 + DOMPurify 净化)
 * - 代码块语法高亮 (highlight.js, 主题随 dark mode 切换)
 * - assistant 消息底部展示来源标注
 * - hover 时显示复制按钮, 点击复制原文, 提供 "已复制" 反馈
 * - 右下角展示时间戳
 * - 支持暗黑模式
 */
import { computed, ref, onBeforeUnmount, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'

// 引入 highlight.js 常用语言 (按需注册, 减小打包体积)
// 注意: 这里只引入实际项目中常见的几种, 后续可按需扩展
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml' // HTML 复用
import css from 'highlight.js/lib/languages/css'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import markdown from 'highlight.js/lib/languages/markdown'
import yaml from 'highlight.js/lib/languages/yaml'
import shell from 'highlight.js/lib/languages/shell'

// 引入主题样式 (github 用于浅色, github-dark 用于深色)
// 由于需要随主题切换, 这里同时引入两个 CSS, 通过容器 class 控制可见性
import 'highlight.js/styles/github.css'
import 'highlight.js/styles/github-dark.css'

// 注册语言 (幂等)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', shell)
hljs.registerLanguage('json', json)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('css', css)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)

// 配置 marked:
// 1. 启用 GFM (GitHub Flavored Markdown)
// 2. 自定义 renderer, 让 code 块自动接入 highlight.js 高亮
marked.setOptions({
  gfm: true,
  breaks: true,
})

const renderer = new marked.Renderer()
// 重写 code 渲染, 自动调用 highlight.js 高亮
renderer.code = function (codeObjOrString, infostring) {
  // marked v14 将 code 签名改为 ({ text, lang, escaped })
  // 为兼容旧版 (v9), 这里做适配判断
  let text, lang
  if (typeof codeObjOrString === 'object' && codeObjOrString !== null) {
    text = codeObjOrString.text ?? ''
    lang = codeObjOrString.lang ?? ''
  } else {
    text = codeObjOrString
    lang = infostring ?? ''
  }

  // 去掉末尾换行 (marked 解析后常带 \n)
  const raw = String(text).replace(/\n$/, '')
  const language = (lang || '').trim().toLowerCase()
  let highlighted
  if (language && hljs.getLanguage(language)) {
    try {
      highlighted = hljs.highlight(raw, { language, ignoreIllegals: true }).value
    } catch (e) {
      highlighted = escapeHtml(raw)
    }
  } else {
    try {
      highlighted = hljs.highlightAuto(raw).value
    } catch (e) {
      highlighted = escapeHtml(raw)
    }
  }
  // 使用 template literal 拼接 class, 便于通过 .dark 高亮样式覆盖
  return `<pre class="hljs"><code class="language-${escapeHtml(language || 'plaintext')}">${highlighted}</code></pre>`
}
marked.use({ renderer })

/**
 * 转义 HTML 特殊字符
 * 防止非代码块区域的原始文本被错误解析为 HTML
 *
 * @param {string} str - 原始字符串
 * @returns {string} 转义后的字符串
 */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 消息数据对象
 *
 * @typedef {Object} SourceItem
 * @property {string} doc_title  - 来源文档标题
 * @property {string} source_id  - 来源 ID
 * @property {string} source_type - 来源类型
 * @property {number} [score]    - 相似度分数
 *
 * @typedef {Object} MessageItem
 * @property {string} id         - 消息唯一 ID
 * @property {'user'|'assistant'} role  - 消息角色
 * @property {string} content    - 消息内容 (Markdown 原文)
 * @property {SourceItem[]} [sources]  - 来源列表 (仅 assistant 可能存在)
 * @property {string} created_at - ISO 格式创建时间
 */
const props = defineProps({
  message: {
    type: Object,
    required: true,
    validator: (val) => {
      return (
        val &&
        typeof val.id === 'string' &&
        typeof val.role === 'string' &&
        typeof val.content === 'string'
      )
    },
  },
})

/** 复制状态: 'idle' 默认, 'copied' 已复制 */
const COPY_STATE = Object.freeze({
  IDLE: 'idle',
  COPIED: 'copied',
})
const copyState = ref(COPY_STATE.IDLE)
/** 复制反馈定时器 ID, 用于在卸载或重复点击时清理 */
let copyTimer = null
/** "已复制" 提示持续时间 (毫秒) */
const COPIED_HINT_DURATION_MS = 2000

/** 是否为用户消息 */
const isUser = computed(() => props.message.role === 'user')

/** 气泡样式: user 蓝色靠右, assistant 白色/深灰靠左 */
const bubbleClass = computed(() => {
  if (isUser.value) {
    return 'bg-blue-600 text-white rounded-br-sm'
  }
  return 'bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100 rounded-bl-sm'
})

/** 是否有可显示的来源 */
const hasSources = computed(() => {
  const sources = props.message.sources
  return Array.isArray(sources) && sources.length > 0
})

/**
 * 将 Markdown 文本解析为净化后的 HTML
 * - 使用 marked 解析 Markdown
 * - 使用 DOMPurify 过滤潜在的 XSS 注入
 * - 失败时返回空串, 由模板走纯文本兜底
 */
const renderedHtml = computed(() => {
  const text = props.message.content
  if (!text) return ''
  try {
    // 1. 解析 Markdown 为 HTML (renderer 已注入代码高亮)
    const rawHtml = marked.parse(text)
    // 2. 净化 (DOMPurify 默认禁止 <script> 等危险标签与属性)
    //    使用 ADD_TAGS 允许 pre/code 标签 (marked 已生成)
    //    使用 ADD_ATTR 允许 class 属性 (高亮 token 需 class)
    const cleanHtml = DOMPurify.sanitize(rawHtml, {
      ADD_TAGS: ['pre', 'code', 'span'],
      ADD_ATTR: ['class'],
    })
    return cleanHtml
  } catch (e) {
    // 解析失败时返回空串, 由模板 fallback 到纯文本展示
    return ''
  }
})

/**
 * 格式化时间戳为 HH:MM 形式
 * - 解析失败时返回原始字符串 (保留可读性)
 * - 空值时返回空串
 */
const formattedTime = computed(() => {
  const iso = props.message.created_at
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
})

/**
 * 清除复制反馈定时器
 *
 * @returns {void}
 */
function clearCopyTimer() {
  if (copyTimer) {
    clearTimeout(copyTimer)
    copyTimer = null
  }
}

/**
 * 复制原文到剪贴板 (使用临时 textarea + execCommand)
 * 兜底方案, 用于 navigator.clipboard 不可用时 (例如非安全上下文).
 *
 * @param {string} text - 待复制的文本
 * @returns {boolean} 是否复制成功
 */
function legacyCopy(text) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'absolute'
  ta.style.left = '-9999px'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch (e) {
    ok = false
  } finally {
    document.body.removeChild(ta)
  }
  return ok
}

/**
 * 复制原文到剪贴板
 * - 优先使用 navigator.clipboard (现代浏览器, HTTPS 或 localhost)
 * - 兜底使用临时 textarea + document.execCommand('copy')
 * - 成功后切换 copyState 为 'copied', 2 秒后还原
 * - 失败时静默处理, 不抛异常 (避免影响用户浏览)
 *
 * @returns {Promise<void>}
 */
async function handleCopy() {
  const text = props.message.content || ''
  let success = false
  try {
    if (navigator.clipboard && window.isSecureContext !== false) {
      await navigator.clipboard.writeText(text)
      success = true
    } else {
      success = legacyCopy(text)
    }
  } catch (e) {
    success = false
  }

  if (success) {
    copyState.value = COPY_STATE.COPIED
    // 清理旧定时器, 避免快速重复点击时状态错乱
    clearCopyTimer()
    copyTimer = setTimeout(() => {
      copyState.value = COPY_STATE.IDLE
      copyTimer = null
    }, COPIED_HINT_DURATION_MS)
  }
}

// 监听 message.content 变化, 若内容更新则立即重置复制状态
watch(
  () => props.message.content,
  () => {
    if (copyState.value === COPY_STATE.COPIED) {
      clearCopyTimer()
      copyState.value = COPY_STATE.IDLE
    }
  },
)

// 组件卸载时清理定时器, 防止内存泄漏
onBeforeUnmount(() => {
  clearCopyTimer()
})
</script>

<style>
/*
  兼容暗黑模式的代码块样式:
  - 浅色模式 (无 .dark): 使用 github 浅色主题 (已在 import 中引入)
  - 暗黑模式 (.dark): 通过 CSS 覆盖 github-dark 主题
*/
.markdown-body pre.hljs {
  padding: 0.75rem 1rem;
  border-radius: 0.375rem;
  overflow-x: auto;
  font-size: 0.8125rem;
  line-height: 1.5;
  margin: 0.5rem 0;
}

.markdown-body code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
}

.markdown-body :not(pre) > code {
  background-color: rgba(135, 131, 120, 0.15);
  border-radius: 0.25rem;
  padding: 0.1rem 0.3rem;
  font-size: 0.85em;
}

.markdown-body p {
  margin: 0.4rem 0;
}

.markdown-body p:first-child { margin-top: 0; }
.markdown-body p:last-child { margin-bottom: 0; }

.markdown-body ul,
.markdown-body ol {
  margin: 0.4rem 0;
  padding-left: 1.5rem;
}

.markdown-body ul { list-style: disc; }
.markdown-body ol { list-style: decimal; }

.markdown-body li { margin: 0.15rem 0; }

.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4 {
  font-weight: 600;
  margin: 0.75rem 0 0.4rem;
  line-height: 1.3;
}

.markdown-body h1 { font-size: 1.25rem; }
.markdown-body h2 { font-size: 1.15rem; }
.markdown-body h3 { font-size: 1.05rem; }
.markdown-body h4 { font-size: 1rem; }

.markdown-body a {
  color: #2563eb;
  text-decoration: underline;
}

.markdown-body blockquote {
  border-left: 3px solid #d1d5db;
  padding-left: 0.75rem;
  color: #6b7280;
  margin: 0.5rem 0;
}

.markdown-body table {
  border-collapse: collapse;
  margin: 0.5rem 0;
  font-size: 0.85em;
}

.markdown-body th,
.markdown-body td {
  border: 1px solid #d1d5db;
  padding: 0.3rem 0.6rem;
}

/* 暗黑模式适配 */
:where(.dark) .markdown-body :not(pre) > code {
  background-color: rgba(135, 131, 120, 0.3);
}

:where(.dark) .markdown-body a {
  color: #60a5fa;
}

:where(.dark) .markdown-body blockquote {
  border-left-color: #4b5563;
  color: #9ca3af;
}

:where(.dark) .markdown-body th,
:where(.dark) .markdown-body td {
  border-color: #4b5563;
}

/* 暗黑模式下, 使用 github-dark 主题的高亮颜色 */
:where(.dark) .markdown-body pre.hljs {
  background: #0d1117;
  color: #c9d1d9;
}
:where(.dark) .markdown-body pre.hljs code { color: #c9d1d9; }

/* 浅色模式下, 沿用 github 浅色主题背景 */
.markdown-body pre.hljs {
  background: #f6f8fa;
  color: #24292f;
}
.markdown-body pre.hljs code { color: #24292f; }
</style>

/**
 * Markdown 渲染 composable
 *
 * 封装 marked 配置、highlight.js 代码高亮注册以及 XSS 防护 (DOMPurify),
 * 提供 renderMarkdown(text) → HTML 的单一接口。
 *
 * 此模块从 ChatMessage.vue 提取而来, 使得 Markdown 渲染能力
 * 可在其他组件 (如通知预览、文档详情) 中复用。
 */

import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'

// ---- 按需注册 highlight.js 常用语言 (减小打包体积) ----
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import markdown from 'highlight.js/lib/languages/markdown'
import yaml from 'highlight.js/lib/languages/yaml'
import shell from 'highlight.js/lib/languages/shell'

import 'highlight.js/styles/github.css'
import 'highlight.js/styles/github-dark.css'

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

// ---- 配置 marked ----
marked.setOptions({ gfm: true, breaks: true })

const renderer = new marked.Renderer()
renderer.code = function (codeObjOrString, infostring) {
  let text, lang
  if (typeof codeObjOrString === 'object' && codeObjOrString !== null) {
    text = codeObjOrString.text ?? ''
    lang = codeObjOrString.lang ?? ''
  } else {
    text = codeObjOrString
    lang = infostring ?? ''
  }

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
  return `<pre class="hljs"><code class="language-${escapeHtml(language || 'plaintext')}">${highlighted}</code></pre>`
}
marked.use({ renderer })

/**
 * 转义 HTML 特殊字符
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
 * 将 Markdown 文本解析为净化后的 HTML
 * - 使用 marked 解析 Markdown
 * - 使用 DOMPurify 过滤潜在的 XSS 注入
 * - 失败时返回空串
 *
 * @param {string} text - Markdown 原文
 * @returns {string} 净化后的 HTML; 空文本或解析失败时返回空串
 */
export function renderMarkdown(text) {
  if (!text) return ''
  try {
    const rawHtml = marked.parse(text)
    return DOMPurify.sanitize(rawHtml, {
      ADD_TAGS: ['pre', 'code', 'span'],
      ADD_ATTR: ['class'],
    })
  } catch (e) {
    return ''
  }
}

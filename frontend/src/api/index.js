/**
 * API 客户端
 *
 * 封装 fetch 与统一错误处理,提供 apiGet / apiPost / apiDelete 三个具名方法.
 * 内置 AbortController 超时机制,区分网络错误/超时/HTTP 错误.
 * 业务调用方通过 endpoints.js 间接使用,无需关心底层协议.
 */

const API_KEY = import.meta.env.VITE_API_KEY || ''
/** API 基础路径，生产环境通过 nginx 代理 */
const BASE_PATH = import.meta.env.VITE_API_BASE || '/zrag'
/** fetch 默认超时时间 (毫秒), 超时后抛出 TIMEOUT 错误 */
const DEFAULT_TIMEOUT_MS = 60000

/**
 * API 调用错误
 *
 * 用于在 fetch 失败或 HTTP 非 2xx 时携带后端约定的 errorCode / status 字段,
 * 业务层可基于 errorCode 区分错误类型 (如未授权 / 限流 / 服务异常).
 *
 * @extends Error
 */
export class ApiError extends Error {
  /**
   * 构造 API 错误实例
   *
   * @param {string} message - 错误描述信息
   * @param {string} errorCode - 后端约定的错误码
   * @param {number} status - HTTP 状态码
   */
  constructor(message, errorCode, status, requestId = '') {
    super(message)
    this.name = 'ApiError'
    this.errorCode = errorCode
    this.status = status
    this.requestId = requestId
  }
}

/**
 * 解析 fetch 响应体为 JSON
 *
 * 兼容空响应体与非 JSON 响应: 解析失败时返回 null 而不抛错.
 *
 * @param {Response} response - fetch 响应对象
 * @returns {Promise<*>} 解析后的数据; 无法解析时返回 null
 */
async function parseJsonResponse(response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/**
 * 发起一次 API 请求
 *
 * 自动注入 JSON 请求头与可选的 Bearer 鉴权,内置 AbortController 超时机制.
 * 统一捕获非 2xx 响应、网络错误、超时并抛出 ApiError.
 * 成功时从约定的 `{ Data, Message, ErrorCode }` 包装中提取 Data 字段返回.
 *
 * @param {string} method - HTTP 方法, 如 'GET' / 'POST' / 'DELETE'
 * @param {string} path - 请求路径, 以 '/' 开头
 * @param {*} [body] - 请求体, 传入时会自动 JSON.stringify
 * @returns {Promise<*>} 后端返回的 Data 字段; 无数据时为 null
 * @throws {ApiError} HTTP 非 2xx / 超时 / 网络错误时抛出
 */
async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  if (API_KEY) headers['Authorization'] = `Bearer ${API_KEY}`

  const options = { method, headers }
  if (body !== undefined) options.body = JSON.stringify(body)

  // AbortController 超时控制
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
  options.signal = controller.signal

  let response
  try {
    response = await fetch(`${BASE_PATH}${path}`, options)
  } catch (e) {
    clearTimeout(timeoutId)
    if (e.name === 'AbortError') {
      throw new ApiError('请求超时，请稍后重试', 'TIMEOUT', 0)
    }
    // TypeError: fetch 本身失败 (网络不可达 / CORS 等)
    throw new ApiError('网络连接失败，请检查网络', 'NETWORK-ERROR', 0)
  }
  clearTimeout(timeoutId)

  const data = await parseJsonResponse(response)
  const requestId = response.headers.get('X-Request-ID') || data?.RequestID || ''

  if (!response.ok) {
    throw new ApiError(
      data?.Message || `HTTP ${response.status}`,
      data?.ErrorCode || 'HTTP-ERROR',
      response.status,
      requestId,
    )
  }
  return data?.Data ?? null
}

/**
 * 根据 errorCode / HTTP 状态码映射为对用户友好的错误消息
 *
 * 优先使用后端返回的 errorCode 做分类, errorCode 不匹配时回退到 HTTP 状态码分类,
 * 最终兜底返回原始 error.message.
 *
 * @param {Error|ApiError} error - 捕获到的异常对象
 * @returns {string} 用户可读的错误描述
 */
export function getUserMessage(error) {
  const code = error?.errorCode || ''
  const status = error?.status || 0

  // 优先按 errorCode 分类
  const codeMap = {
    'UNAUTHORIZED': '认证失败，请刷新页面重试',
    'NOT-FOUND': '请求的资源不存在',
    'LLM-CALL-ERROR': 'AI 服务暂时不可用，请稍后重试',
    'RETRIEVAL-ERROR': '知识库检索异常，请稍后重试',
    'INGESTION-ERROR': '文档摄入失败，请稍后重试',
    'INTERNAL-ERROR': '服务器内部错误，请稍后重试',
    'PARSE-ERROR': '请求格式错误',
    'VALIDATION-ERROR': '请求参数有误',
    'API-ERROR': '服务异常，请稍后重试',
    'TIMEOUT': '请求超时，请稍后重试',
    'NETWORK-ERROR': '网络连接失败，请检查网络',
  }
  if (code && codeMap[code]) return codeMap[code]

  // 按 HTTP 状态码分类
  if (status === 401) return '认证失败，请刷新页面重试'
  if (status === 404) return '请求的资源不存在'
  if (status === 502) return 'AI 服务暂时不可用，请稍后重试'
  if (status === 429) return '请求过于频繁，请稍后重试'
  if (status >= 500) return '服务器内部错误，请稍后重试'

  // 兜底: 返回原始 message，末尾追加 Trace ID
  const base = error?.message || '未知错误'
  const suffix = error?.requestId ? ` (错误ID: ${error.requestId})` : ''
  return base + suffix
}

/**
 * GET 请求
 *
 * @param {string} path - 请求路径
 * @returns {Promise<*>} 响应 Data 字段
 */
export const apiGet = (path) => request('GET', path)

/**
 * POST 请求
 *
 * @param {string} path - 请求路径
 * @param {*} body - 请求体 (会被 JSON 序列化)
 * @returns {Promise<*>} 响应 Data 字段
 */
export const apiPost = (path, body) => request('POST', path, body)

/**
 * DELETE 请求
 *
 * @param {string} path - 请求路径
 * @returns {Promise<*>} 响应 Data 字段
 */
export const apiDelete = (path) => request('DELETE', path)

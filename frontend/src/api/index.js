/**
 * API 客户端
 *
 * 封装 fetch 与统一错误处理,提供 apiGet / apiPost / apiDelete 三个具名方法.
 * 业务调用方通过 endpoints.js 间接使用,无需关心底层协议.
 */

const API_KEY = import.meta.env.VITE_API_KEY || ''
/** API 基础路径，生产环境通过 nginx 代理 */
const BASE_PATH = import.meta.env.VITE_API_BASE || '/zrag'

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
  constructor(message, errorCode, status) {
    super(message)
    this.name = 'ApiError'
    this.errorCode = errorCode
    this.status = status
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
 * 自动注入 JSON 请求头与可选的 Bearer 鉴权,统一捕获非 2xx 响应并抛出 ApiError.
 * 成功时从约定的 `{ Data, Message, ErrorCode }` 包装中提取 Data 字段返回.
 *
 * @param {string} method - HTTP 方法, 如 'GET' / 'POST' / 'DELETE'
 * @param {string} path - 请求路径, 以 '/' 开头
 * @param {*} [body] - 请求体, 传入时会自动 JSON.stringify
 * @returns {Promise<*>} 后端返回的 Data 字段; 无数据时为 null
 * @throws {ApiError} HTTP 非 2xx 时抛出
 */
async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  if (API_KEY) headers['Authorization'] = `Bearer ${API_KEY}`

  const options = { method, headers }
  if (body !== undefined) options.body = JSON.stringify(body)

  const response = await fetch(`${BASE_PATH}${path}`, options)
  const data = await parseJsonResponse(response)

  if (!response.ok) {
    throw new ApiError(
      data?.Message || `HTTP ${response.status}`,
      data?.ErrorCode || 'HTTP-ERROR',
      response.status,
    )
  }
  return data?.Data ?? null
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

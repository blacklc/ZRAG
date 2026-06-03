// API 客户端 - 封装 fetch 与错误处理
const API_KEY = import.meta.env.VITE_API_KEY || ''

export class ApiError extends Error {
  constructor(message, errorCode, status) {
    super(message)
    this.name = 'ApiError'
    this.errorCode = errorCode
    this.status = status
  }
}

async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  if (API_KEY) headers['Authorization'] = `Bearer ${API_KEY}`
  const options = { method, headers }
  if (body !== undefined) options.body = JSON.stringify(body)
  const response = await fetch(path, options)
  const text = await response.text()
  let data
  try { data = text ? JSON.parse(text) : null } catch { data = null }
  if (!response.ok) {
    throw new ApiError(
      data?.Message || `HTTP ${response.status}`,
      data?.ErrorCode || 'HTTP-ERROR',
      response.status
    )
  }
  return data?.Data ?? null
}

export const apiGet = (path) => request('GET', path)
export const apiPost = (path, body) => request('POST', path, body)
export const apiDelete = (path) => request('DELETE', path)

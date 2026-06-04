/**
 * API 客户端单元测试
 *
 * 覆盖 ApiError 构造、apiGet / apiPost / apiDelete 请求格式、
 * API Key 鉴权头、非 JSON 响应、HTTP 错误响应以及标准 APIResponse 封装.
 */

import { describe, expect, it, vi, afterAll, beforeEach } from 'vitest'
import { ApiError } from '../../api/index.js'

const originalFetch = globalThis.fetch

afterAll(() => {
  globalThis.fetch = originalFetch
})

describe('ApiError', () => {
  it('应正确构造 ApiError 实例', () => {
    const error = new ApiError('test message', 'ERR-001', 400)

    expect(error).toBeInstanceOf(Error)
    expect(error.name).toBe('ApiError')
    expect(error.message).toBe('test message')
    expect(error.errorCode).toBe('ERR-001')
    expect(error.status).toBe(400)
  })

  it('应保留 Error.prototype 的属性和方法', () => {
    const error = new ApiError('msg', 'ERR-002', 500)

    expect(error.stack).toBeDefined()
    expect(error.toString()).toContain('ApiError')
  })

  it('在不传 errorCode 时应为 undefined', () => {
    const error = new ApiError('msg', undefined, 500)

    expect(error.errorCode).toBeUndefined()
  })
})

describe('apiGet', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('应发起 GET 请求并返回 Data 字段', async () => {
    const mockBody = { id: 1, name: 'test' }
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () =>
        Promise.resolve(
          JSON.stringify({ Data: mockBody, Message: 'ok', ErrorCode: '' }),
        ),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')
    const result = await apiGet('/v1/conversations')

    expect(mockFetch).toHaveBeenCalledWith('/zrag/v1/conversations', {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    })
    expect(result).toEqual(mockBody)
  })

  it('当 Data 为 null 时应返回 null', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ Data: null })),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')
    const result = await apiGet('/v1/test')

    expect(result).toBeNull()
  })

  it('响应中缺少 Data 字段时应返回 null', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ Message: 'no data' })),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')
    const result = await apiGet('/v1/test')

    expect(result).toBeNull()
  })
})

describe('apiPost', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('应发起 POST 请求并传入 JSON 序列化的 body', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ Data: { id: 'new' } })),
    })
    globalThis.fetch = mockFetch

    const { apiPost } = await import('../../api/index.js')
    const body = { query: 'hello' }
    const result = await apiPost('/v1/conversations', body)

    expect(mockFetch).toHaveBeenCalledWith('/zrag/v1/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    expect(result).toEqual({ id: 'new' })
  })

  it('当 body 未传入时不应包含 body 字段', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ Data: null })),
    })
    globalThis.fetch = mockFetch

    const { apiPost } = await import('../../api/index.js')
    await apiPost('/v1/test')

    const callArgs = mockFetch.mock.calls[0][1]
    expect(callArgs.body).toBeUndefined()
  })
})

describe('apiDelete', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('应发起 DELETE 请求', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ Data: null })),
    })
    globalThis.fetch = mockFetch

    const { apiDelete } = await import('../../api/index.js')
    const result = await apiDelete('/v1/conversations/conv-1')

    expect(mockFetch).toHaveBeenCalledWith('/zrag/v1/conversations/conv-1', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
    })
    expect(result).toBeNull()
  })
})

describe('API Key 鉴权头', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('当 VITE_API_KEY 存在时应携带 Authorization header', async () => {
    vi.stubEnv('VITE_API_KEY', 'test-key-value')

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ Data: {} })),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')
    await apiGet('/v1/test')

    expect(mockFetch).toHaveBeenCalledWith('/zrag/v1/test', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer test-key-value',
      },
    })

    vi.unstubAllEnvs()
  })
})

describe('非 JSON 响应', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('响应体为非 JSON 字符串时 data 应为 null', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('not a json string'),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')
    const result = await apiGet('/v1/test')

    expect(result).toBeNull()
  })

  it('空响应体时 data 应为 null', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(''),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')
    const result = await apiGet('/v1/test')

    expect(result).toBeNull()
  })
})

describe('HTTP 错误响应', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('非 2xx 状态码应抛出 ApiError', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            ErrorCode: 'FORBIDDEN',
            Message: 'Access denied',
          }),
        ),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')

    await expect(apiGet('/v1/test')).rejects.toMatchObject({
      name: 'ApiError',
      message: 'Access denied',
      errorCode: 'FORBIDDEN',
      status: 403,
    })
  })

  it('响应体无 Message 时应使用默认错误消息', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve(''),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')

    await expect(apiGet('/v1/test')).rejects.toMatchObject({
      message: 'HTTP 500',
      errorCode: 'HTTP-ERROR',
      status: 500,
    })
  })

  it('响应体无 ErrorCode 时应使用默认错误码', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve(JSON.stringify({})),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')

    await expect(apiGet('/v1/test')).rejects.toMatchObject({
      errorCode: 'HTTP-ERROR',
    })
  })
})

describe('标准 APIResponse 封装', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('完整 APIResponse 结构应解包 Data 字段', async () => {
    const apiResponse = {
      Data: { items: ['a', 'b'] },
      Message: 'success',
      ErrorCode: '',
      RequestID: 'req-abc-123',
    }
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify(apiResponse)),
    })
    globalThis.fetch = mockFetch

    const { apiGet } = await import('../../api/index.js')
    const result = await apiGet('/v1/test')

    expect(result).toEqual({ items: ['a', 'b'] })
  })
})

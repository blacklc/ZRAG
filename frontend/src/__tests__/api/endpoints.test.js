/**
 * API 端点函数单元测试
 *
 * Mock apiGet / apiPost / apiDelete 后验证每个端点函数是否正确调用底层函数和路径.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest'

// 在 import endpoints 之前 mock index.js
vi.mock('../../api/index.js', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}))

import {
  listConversations,
  createConversation,
  getMessages,
  addMessage,
  deleteConversation,
  ingestDocuments,
  listSources,
  getHealthLive,
  getHealthReady,
} from '../../api/endpoints.js'

import { apiGet, apiPost, apiDelete } from '../../api/index.js'

describe('端点函数', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listConversations 应调用 apiGet("/v1/conversations")', () => {
    listConversations()

    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/v1/conversations')
  })

  it('createConversation 应调用 apiPost("/v1/conversations", { query })', () => {
    createConversation('hello')

    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(apiPost).toHaveBeenCalledWith('/v1/conversations', { query: 'hello' })
  })

  it('getMessages 应调用 apiGet("/v1/conversations/{id}/messages")', () => {
    getMessages('conv-1')

    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/v1/conversations/conv-1/messages')
  })

  it('addMessage 应调用 apiPost("/v1/conversations/{id}/messages", { query })', () => {
    addMessage('conv-1', 'hello')

    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(apiPost).toHaveBeenCalledWith(
      '/v1/conversations/conv-1/messages',
      { query: 'hello' },
    )
  })

  it('deleteConversation 应调用 apiDelete("/v1/conversations/{id}")', () => {
    deleteConversation('conv-1')

    expect(apiDelete).toHaveBeenCalledTimes(1)
    expect(apiDelete).toHaveBeenCalledWith('/v1/conversations/conv-1')
  })

  it('ingestDocuments 应调用 apiPost("/v1/documents/ingest", payload)', () => {
    const payload = { source_type: 'mac_notes', full: true }
    ingestDocuments(payload)

    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(apiPost).toHaveBeenCalledWith('/v1/documents/ingest', payload)
  })

  it('listSources 应调用 apiGet("/v1/sources")', () => {
    listSources()

    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/v1/sources')
  })

  it('getHealthLive 应调用 apiGet("/v1/health/live")', () => {
    getHealthLive()

    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/v1/health/live')
  })

  it('getHealthReady 应调用 apiGet("/v1/health/ready")', () => {
    getHealthReady()

    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/v1/health/ready')
  })
})

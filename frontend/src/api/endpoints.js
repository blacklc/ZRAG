/**
 * 后端 API 端点定义
 *
 * 所有路径统一从此处导出, 业务组件只依赖具名函数, 不直接出现字符串路径,
 * 便于后端路由调整时集中修改.
 */

import { apiGet, apiPost, apiDelete } from './index.js'

/**
 * 获取会话列表
 *
 * @returns {Promise<Array<{id: string, title: string, created_at: string, last_msg_at?: string}>>}
 */
export const listConversations = () => apiGet('/v1/conversations')

/**
 * 创建新会话并发起首次提问
 *
 * @param {string} query - 用户输入的查询文本
 * @returns {Promise<{id: string, title?: string}>} 新建会话对象
 */
export const createConversation = (query) => apiPost('/v1/conversations', { query })

/**
 * 获取指定会话的全部消息
 *
 * @param {string} conversationId - 会话 ID
 * @returns {Promise<Array<{id: string, role: string, content: string, created_at: string, sources?: Array<*>}>>}
 */
export const getMessages = (conversationId) =>
  apiGet(`/v1/conversations/${conversationId}/messages`)

/**
 * 向指定会话追加一条消息
 *
 * @param {string} conversationId - 会话 ID
 * @param {string} query - 用户输入的查询文本
 * @returns {Promise<*>} 后端响应数据
 */
export const addMessage = (conversationId, query) =>
  apiPost(`/v1/conversations/${conversationId}/messages`, { query })

/**
 * 删除指定会话
 *
 * @param {string} conversationId - 会话 ID
 * @returns {Promise<*>} 后端响应数据
 */
export const deleteConversation = (conversationId) =>
  apiDelete(`/v1/conversations/${conversationId}`)

/**
 * 触发文档摄入
 *
 * @param {{source_type: string|null, full: boolean}} payload - 摄入参数
 *   - source_type: 指定来源类型; 传 null 表示对所有来源执行
 *   - full: true 表示全量摄入, false 表示增量摄入
 * @returns {Promise<{processed?: number, added?: number, skipped?: number, failed?: number}>}
 */
export const ingestDocuments = (payload) => apiPost('/v1/documents/ingest', payload)

/**
 * 获取知识库来源列表
 *
 * @returns {Promise<Array<{source_type: string, doc_count: number, last_imported?: string}>>}
 */
export const listSources = () => apiGet('/v1/sources')

/**
 * 存活探针 (liveness)
 *
 * @returns {Promise<*>} 后端响应数据
 */
export const getHealthLive = () => apiGet('/v1/health/live')

/**
 * 就绪探针 (readiness)
 *
 * @returns {Promise<*>} 后端响应数据
 */
export const getHealthReady = () => apiGet('/v1/health/ready')

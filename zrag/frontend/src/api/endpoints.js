import { apiGet, apiPost, apiDelete } from './index.js'

export const listConversations = () => apiGet('/v1/conversations')
export const createConversation = (query) => apiPost('/v1/conversations', { query })
export const getMessages = (conversationId) => apiGet(`/v1/conversations/${conversationId}/messages`)
export const addMessage = (conversationId, query) => apiPost(`/v1/conversations/${conversationId}/messages`, { query })
export const deleteConversation = (conversationId) => apiDelete(`/v1/conversations/${conversationId}`)
export const ingestDocuments = (payload) => apiPost('/v1/documents/ingest', payload)
export const listSources = () => apiGet('/v1/sources')
export const getHealthLive = () => apiGet('/v1/health/live')
export const getHealthReady = () => apiGet('/v1/health/ready')

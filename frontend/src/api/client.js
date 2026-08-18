const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(body = {}, status = 0) {
    super(body.message || '请求失败')
    this.code = body.code || (status ? 'HTTP_ERROR' : 'NETWORK_ERROR')
    this.traceId = body.trace_id || ''
    this.status = status
  }
}

export async function apiRequest(path, options = {}) {
  let response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    })
  } catch {
    throw new ApiError()
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok || body.code !== 'OK') throw new ApiError(body, response.status)
  return body.data
}

export function withQuery(path, values) {
  const query = new URLSearchParams(Object.entries(values).filter(([, value]) => value !== '' && value != null))
  return `${path}${query.size ? `?${query}` : ''}`
}

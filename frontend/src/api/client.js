const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

const errorMessages = {
  DATABASE_UNAVAILABLE: '数据服务暂时不可用，请稍后重试。',
  RESULT_NOT_READY: '该分析结果尚未发布。',
  SERVER_MISCONFIGURED: '服务配置不完整，暂时无法提供数据。',
  SERVICE_RESULT_INVALID: '分析结果格式无法验证。',
  UPSTREAM_SERVICE_ERROR: '上游分析服务暂时不可用。',
  NETWORK_ERROR: '无法连接后端服务，请检查服务是否已启动。',
  INVALID_QUERY_PARAMETER: '筛选值不受支持。',
  INVALID_REQUEST_FIELD: '请求字段不受支持。',
  INVALID_REQUEST_FORMAT: '请求格式不受支持。',
  LEAKAGE_FIELD_FORBIDDEN: '请求包含不允许使用的出院后或目标字段。',
  INVALID_FEATURE_VALUE: '预测字段的取值不受支持。',
  INCONSISTENT_DATA_VERSION: '关联分析批次不一致，已停止展示混合数据。',
  HTTP_ERROR: '数据服务返回了暂时无法处理的响应。',
  INTERNAL_ERROR: '数据服务内部出现异常。',
}

export function getApiErrorMessage(error) {
  return errorMessages[error?.code] || '数据加载失败，请稍后重试。'
}

export function isAbortError(error) {
  return error?.name === 'AbortError'
}

export class ApiError extends Error {
  constructor(body = {}, status = 0, cause) {
    super(body.message || '请求失败')
    this.code = body.code || (status ? 'HTTP_ERROR' : 'NETWORK_ERROR')
    this.traceId = body.trace_id || ''
    this.details = body.details || null
    this.status = status
    this.cause = cause
  }
}

export async function apiRequest(path, options = {}) {
  let response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
  } catch (cause) {
    if (isAbortError(cause)) throw cause
    throw new ApiError({}, 0, cause)
  }
  const body = await response.json().catch(() => null)
  if (!body || !response.ok || body.code !== 'OK') throw new ApiError(body || {}, response.status)
  return body.data
}

export function withQuery(path, values) {
  const query = new URLSearchParams(Object.entries(values).filter(([, value]) => value !== '' && value != null))
  return `${path}${query.size ? `?${query}` : ''}`
}

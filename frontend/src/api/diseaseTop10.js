export const TOP10_API_PATH = '/api/v1/diseases/top10'

const configuredBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '')

const errorMessages = {
  INVALID_QUERY_PARAMETER: '接口不接受查询参数。',
  INVALID_REQUEST_FORMAT: '请求格式无效。',
  METHOD_NOT_ALLOWED: '当前接口不支持该请求方式。',
  RESOURCE_NOT_FOUND: '请求的资源不存在。',
  DATABASE_UNAVAILABLE: '数据服务暂时不可用，请检查数据库连接。',
  RESULT_NOT_READY: '疾病 TOP10 结果尚未发布。',
  SERVER_MISCONFIGURED: '服务配置不完整，请检查后端环境变量。',
  SERVICE_RESULT_INVALID: '已发布服务结果校验失败。',
  INTERNAL_ERROR: '服务内部出现异常，请稍后重试。',
}

export class DiseaseTop10ApiError extends Error {
  constructor({ code = 'INTERNAL_ERROR', status = 0, message, traceId = '', cause } = {}) {
    super(message || errorMessages[code] || '数据请求失败，请稍后重试。')
    this.name = 'DiseaseTop10ApiError'
    this.code = code
    this.status = status
    this.traceId = traceId
    this.cause = cause
  }
}

function getApiUrl() {
  return `${configuredBaseUrl}${TOP10_API_PATH}`
}

function statusCodeForResponse(status) {
  if (status === 400) return 'INVALID_REQUEST_FORMAT'
  if (status === 404) return 'RESOURCE_NOT_FOUND'
  if (status === 405) return 'METHOD_NOT_ALLOWED'
  if (status === 503) return 'DATABASE_UNAVAILABLE'
  return 'INTERNAL_ERROR'
}

async function readJson(response) {
  try {
    return await response.json()
  } catch (error) {
    throw new DiseaseTop10ApiError({
      code: 'SERVICE_RESULT_INVALID',
      status: response.status,
      cause: error,
    })
  }
}

function validateData(data) {
  if (!data || typeof data !== 'object') {
    throw new DiseaseTop10ApiError({ code: 'SERVICE_RESULT_INVALID' })
  }

  if (
    data.metric !== 'disease_case_count_top10'
    || data.unit !== 'discharge_records'
    || typeof data.data_version !== 'string'
    || !data.data_version
    || typeof data.generated_at !== 'string'
    || !data.generated_at.endsWith('Z')
    || !Array.isArray(data.items)
    || data.items.length > 10
  ) {
    throw new DiseaseTop10ApiError({ code: 'SERVICE_RESULT_INVALID' })
  }

  for (const item of data.items) {
    if (
      !Number.isInteger(item?.rank)
      || typeof item.diagnosis_name !== 'string'
      || !item.diagnosis_name
      || !Number.isInteger(item.case_count)
      || item.case_count <= 0
    ) {
      throw new DiseaseTop10ApiError({ code: 'SERVICE_RESULT_INVALID' })
    }
  }

  return data
}

export async function fetchDiseaseTop10(fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== 'function') {
    throw new DiseaseTop10ApiError({ code: 'NETWORK_ERROR' })
  }

  let response
  try {
    response = await fetchImpl(getApiUrl(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
  } catch (error) {
    throw new DiseaseTop10ApiError({ code: 'NETWORK_ERROR', cause: error })
  }

  const body = await readJson(response)
  if (!response.ok) {
    throw new DiseaseTop10ApiError({
      code: body?.code || statusCodeForResponse(response.status),
      status: response.status,
      traceId: body?.trace_id || response.headers?.get?.('X-Trace-ID') || '',
    })
  }

  if (body?.code !== 'OK') {
    throw new DiseaseTop10ApiError({
      code: body?.code || 'SERVICE_RESULT_INVALID',
      status: response.status,
      traceId: body?.trace_id || '',
    })
  }

  return validateData(body.data)
}

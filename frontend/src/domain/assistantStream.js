function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function resultError(message) {
  const error = new Error(message)
  error.code = 'SERVICE_RESULT_INVALID'
  error.userMessage = message
  return error
}

function parseSseBlock(block) {
  let event = 'message'
  const dataLines = []
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
      continue
    }
    throw resultError('流式响应格式无效，未展示回答。请重试。')
  }
  if (!dataLines.length) return null
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    throw resultError('流式响应格式无效，未展示回答。请重试。')
  }
}

async function* readSseEvents(reader) {
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false
  while (!finished) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    buffer = buffer.replace(/\r\n/g, '\n')
    let boundaryIndex = buffer.indexOf('\n\n')
    while (boundaryIndex >= 0) {
      const block = buffer.slice(0, boundaryIndex).replace(/\r$/, '')
      buffer = buffer.slice(boundaryIndex + 2)
      const parsed = parseSseBlock(block)
      if (parsed) yield parsed
      boundaryIndex = buffer.indexOf('\n\n')
    }
    finished = done
  }
  if (buffer.trim()) {
    const parsed = parseSseBlock(buffer.replace(/\r$/, ''))
    if (parsed) yield parsed
  }
}

function streamError(data) {
  const code = normalizeText(data?.code) || 'UPSTREAM_SERVICE_ERROR'
  const message = normalizeText(data?.message) || 'AI 服务暂时不可用，请稍后重试。'
  const error = new Error(message)
  error.code = code
  error.userMessage = message
  error.traceId = normalizeText(data?.trace_id)
  return error
}

export async function consumeAssistantStream(
  response,
  { onStage, onDelta, onDone } = {},
) {
  const reader = response?.body?.getReader?.()
  if (!reader) throw resultError('流式响应不可用，未展示回答。请重试。')

  let receivedDone = false
  try {
    for await (const event of readSseEvents(reader)) {
      if (event.event === 'stage') {
        onStage?.(event.data)
        continue
      }
      if (event.event === 'delta') {
        if (!event.data || typeof event.data.text !== 'string') {
          throw resultError('流式回答内容无效，未展示回答。请重试。')
        }
        onDelta?.(event.data.text)
        continue
      }
      if (event.event === 'error') throw streamError(event.data)
      if (event.event === 'done') {
        if (!event.data || typeof event.data !== 'object') {
          throw resultError('流式结果缺少安全元数据，未展示回答。请重试。')
        }
        const answer = normalizeText(event.data.answer)
        onDone?.(event.data, answer)
        receivedDone = true
        break
      }
      throw resultError('流式事件类型无效，未展示回答。请重试。')
    }
  } finally {
    if (receivedDone) {
      // Cleanup must never delay the terminal UI state.
      Promise.resolve()
        .then(() => reader.cancel?.())
        .catch(() => {})
    }
  }

  if (!receivedDone) throw resultError('流式回答未正常完成，请重试。')
}

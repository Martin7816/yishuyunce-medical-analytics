import test from 'node:test'
import assert from 'node:assert/strict'

import { consumeAssistantStream } from '../src/domain/assistantStream.js'

function responseWithHangingCancel() {
  const encoder = new TextEncoder()
  const payload = [
    'event: stage\ndata: {"stage":"preparing","label":"Preparing"}\n\n',
    'event: delta\ndata: {"text":"Answer"}\n\n',
    'event: done\ndata: {"answer":"Answer"}\n\n',
  ].join('')
  let delivered = false
  return {
    body: {
      getReader() {
        return {
          async read() {
            if (delivered) return new Promise(() => {})
            delivered = true
            return { value: encoder.encode(payload), done: false }
          },
          cancel() {
            return new Promise(() => {})
          },
        }
      },
    },
  }
}

test('done resolves the assistant stream before a hanging reader cleanup', async () => {
  const events = []

  await Promise.race([
    consumeAssistantStream(responseWithHangingCancel(), {
      onStage: data => events.push(['stage', data.stage]),
      onDelta: text => events.push(['delta', text]),
      onDone: (data, answer) => events.push(['done', data.answer, answer]),
    }),
    new Promise((_, reject) => {
      setTimeout(() => reject(new Error('stream completion timed out')), 100)
    }),
  ])

  assert.deepEqual(events, [
    ['stage', 'preparing'],
    ['delta', 'Answer'],
    ['done', 'Answer', 'Answer'],
  ])
})

function responseThatHangsAfterPrematureCompletedStage() {
  const encoder = new TextEncoder()
  const payload = [
    'event: delta\ndata: {"text":"Answer"}\n\n',
    'event: stage\ndata: {"stage":"completed","label":"分析完成"}\n\n',
  ].join('')
  let delivered = false
  return {
    body: {
      getReader() {
        return {
          async read() {
            if (delivered) return new Promise(() => {})
            delivered = true
            return { value: encoder.encode(payload), done: false }
          },
          cancel() {},
        }
      },
    },
  }
}

test('a premature completed stage cannot leave the stream waiting forever for done', async () => {
  await assert.rejects(
    Promise.race([
      consumeAssistantStream(
        responseThatHangsAfterPrematureCompletedStage(),
        { terminalGraceMs: 20 },
      ),
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error('test harness timed out')), 100)
      }),
    ]),
    /完成信号缺少结果元数据/,
  )
})

import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizeVisibleStreamStage,
  resolveSubmitAction,
} from '../src/domain/assistantInteraction.js'

test('a second click is ignored while the first stop request is settling', () => {
  assert.equal(resolveSubmitAction({ loading: true, stopping: false }), 'stop')
  assert.equal(resolveSubmitAction({ loading: true, stopping: true }), 'ignore')
  assert.equal(resolveSubmitAction({ loading: false, stopping: false }), 'send')
})

test('completed is presented as finalizing until the done event is accepted', () => {
  assert.deepEqual(
    normalizeVisibleStreamStage({ stage: 'completed', label: '分析完成' }),
    { stage: 'finalizing', label: '正在完成' },
  )
})

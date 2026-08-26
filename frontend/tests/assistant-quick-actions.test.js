import test from 'node:test'
import assert from 'node:assert/strict'

import { ASSISTANT_QUICK_ACTIONS } from '../src/domain/assistantQuickActions.js'

test('quick actions contain only the four live-verified supported questions', () => {
  assert.deepEqual(
    ASSISTANT_QUICK_ACTIONS.map(action => action.question),
    [
      '概括当前运营情况',
      '当前平均收费和平均成本分别是多少？',
      '疾病病例量排名前十是什么？',
      '高费用模型表现如何？',
    ],
  )
  assert.equal(
    ASSISTANT_QUICK_ACTIONS.some(action => /趋势|原因|预测/.test(action.question)),
    false,
  )
})

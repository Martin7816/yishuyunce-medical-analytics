import test from 'node:test'
import assert from 'node:assert/strict'

import { hasAggregateEvidence } from '../src/domain/assistantEvidence.js'

test('ranking sections are valid aggregate evidence when top-level metrics are empty', () => {
  assert.equal(hasAggregateEvidence([], ['diagnosis_ranking']), true)
})

test('an analytics source without metrics or sections is rejected', () => {
  assert.equal(hasAggregateEvidence([], []), false)
})

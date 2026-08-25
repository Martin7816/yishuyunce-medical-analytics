import test from 'node:test'
import assert from 'node:assert/strict'

import {
  costComparisonDimensionForFilters,
  costComparisonDimensionsForFilters,
} from '../src/domain/costComparison.js'

test('disease selection removes the disease comparison dimension and defaults to hospitals', () => {
  assert.deepEqual(
    costComparisonDimensionsForFilters({ diagnosis_code: 'BLD007' }).map(option => option.key),
    ['facility', 'severity'],
  )
  assert.equal(costComparisonDimensionForFilters({ diagnosis_code: 'BLD007' }, 'diagnosis'), 'facility')
})

test('hospital selection removes the hospital comparison dimension and defaults to diseases', () => {
  assert.deepEqual(
    costComparisonDimensionsForFilters({ facility_id: '123' }).map(option => option.key),
    ['diagnosis', 'severity'],
  )
  assert.equal(costComparisonDimensionForFilters({ facility_id: '123' }, 'facility'), 'diagnosis')
})

test('severity selection removes the severity comparison dimension', () => {
  assert.deepEqual(
    costComparisonDimensionsForFilters({ severity: 'Major' }).map(option => option.key),
    ['diagnosis', 'facility'],
  )
})

test('clearing filters keeps all comparison dimensions and preserves a valid selection', () => {
  assert.deepEqual(
    costComparisonDimensionsForFilters({}).map(option => option.key),
    ['diagnosis', 'facility', 'severity'],
  )
  assert.equal(costComparisonDimensionForFilters({}, 'facility'), 'facility')
})

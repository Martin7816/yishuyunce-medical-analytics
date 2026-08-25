import test from 'node:test'
import assert from 'node:assert/strict'

import { prepareFilterNavigation } from '../src/domain/filterNavigation.js'

const config = {
  filters: [
    { key: 'diagnosis_code' },
    { key: 'facility_id' },
    { key: 'severity' },
  ],
  mutuallyExclusive: ['diagnosis_code', 'facility_id'],
}

test('filter navigation still requests a reload when local state was updated before the URL', () => {
  const navigation = prepareFilterNavigation(
    { diagnosis_code: 'NVS005', facility_id: '', severity: '' },
    config,
    'diagnosis_code',
    'NVS005',
    {},
  )

  assert.equal(navigation.shouldLoad, true)
  assert.deepEqual(navigation.query, { diagnosis_code: 'NVS005' })
})

test('filter navigation clears a mutually exclusive value from the request query', () => {
  const navigation = prepareFilterNavigation(
    { diagnosis_code: '', facility_id: '1', severity: '' },
    config,
    'diagnosis_code',
    'NVS005',
    { facility_id: '1' },
  )

  assert.deepEqual(navigation.values, { diagnosis_code: 'NVS005', facility_id: '', severity: '' })
  assert.deepEqual(navigation.query, { diagnosis_code: 'NVS005' })
  assert.equal(navigation.shouldLoad, true)
})

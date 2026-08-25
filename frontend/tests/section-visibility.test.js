import test from 'node:test'
import assert from 'node:assert/strict'

import { filterSectionsByActiveFilters } from '../src/domain/sectionVisibility.js'

test('age structure is hidden when an age group filter is active', () => {
  const sections = [{ key: 'age' }, { key: 'gender' }, { key: 'admission_type' }]

  assert.deepEqual(
    filterSectionsByActiveFilters(sections, { age_group: '18 to 29' }).map(section => section.key),
    ['gender', 'admission_type'],
  )
})

test('age structure remains visible when no age group filter is active', () => {
  const sections = [{ key: 'age' }, { key: 'gender' }]

  assert.deepEqual(
    filterSectionsByActiveFilters(sections, { age_group: '' }).map(section => section.key),
    ['age', 'gender'],
  )
})

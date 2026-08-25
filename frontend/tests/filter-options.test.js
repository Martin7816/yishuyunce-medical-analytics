import test from 'node:test'
import assert from 'node:assert/strict'

import { optionsForSection, sortOptionsByChineseInitial } from '../src/domain/filterOptions.js'

test('filter options sort by Chinese dictionary order without mutating the source', () => {
  const options = [
    { value: 'HF001', label: '心力衰竭' },
    { value: 'SEP001', label: '败血症' },
    { value: 'PN001', label: '肺炎' },
    { value: 'OTH001', label: '其他' },
  ]

  const result = sortOptionsByChineseInitial(options)

  assert.deepEqual(result.map(option => option.label), ['败血症', '肺炎', '其他', '心力衰竭'])
  assert.deepEqual(options.map(option => option.label), ['心力衰竭', '败血症', '肺炎', '其他'])
})

test('published TOP10 section resolves to clickable filter options in ranking order', () => {
  const options = [
    { value: 'OTHER', rawLabel: 'OTHER DISEASE', label: 'OTHER DISEASE' },
    { value: 'HF001', rawLabel: 'HEART FAILURE', label: '心力衰竭' },
    { value: 'SEP001', rawLabel: 'SEPTICEMIA', label: '败血症' },
    { value: 'PN001', rawLabel: 'PNEUMONIA', label: '肺炎' },
  ]
  const payload = {
    sections: [{
      key: 'top10',
      items: [
        { name: 'SEPTICEMIA', value: 138035 },
        { name: 'HEART FAILURE', value: 58562 },
      ],
    }],
  }

  const result = optionsForSection(options, payload, 'top10')

  assert.deepEqual(result.map(option => option.value), ['SEP001', 'HF001'])
  assert.deepEqual(result.map(option => option.label), ['败血症', '心力衰竭'])
})

test('quick-filter options are empty when the ranking section is unavailable', () => {
  const options = [{ value: 'A', label: 'A' }, { value: 'B', label: 'B' }]
  assert.deepEqual(optionsForSection(options, { sections: [] }, 'top10'), [])
})

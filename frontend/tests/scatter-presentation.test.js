import test from 'node:test'
import assert from 'node:assert/strict'

import {
  scatterLegendLayout,
  scatterPointOffset,
  scatterPointRadius,
} from '../src/domain/scatterPresentation.js'

test('scatter legend wraps before labels leave a narrow chart', () => {
  const layout = scatterLegendLayout(188, 5)

  assert.equal(layout.columns, 3)
  assert.equal(layout.rows, 2)
  assert.ok(layout.top > 34)
  assert.ok((layout.columns * layout.cellWidth) <= 188)
})

test('scatter bubbles keep the largest mark bounded and use area-like scaling', () => {
  assert.equal(scatterPointRadius(0, 100), 4.5)
  assert.equal(scatterPointRadius(100, 100), 11.5)
  assert.ok(scatterPointRadius(25, 100) < scatterPointRadius(50, 100))
})

test('scatter points receive a centered, deterministic separation within a group', () => {
  const offsets = [0, 1, 2, 3, 4].map(index => scatterPointOffset(index, 5))

  assert.deepEqual(offsets, [-9.6, -4.8, 0, 4.8, 9.6])
  assert.equal(scatterPointOffset(0, 1), 0)
})

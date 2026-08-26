import test from 'node:test'
import assert from 'node:assert/strict'

import {
  INSIGHT_REPORT_TITLE,
  PRODUCT_NAME,
  PRODUCT_SHORT_NAME,
  PRODUCT_TAGLINE,
} from '../src/domain/productIdentity.js'

test('product identity exposes one formal name and a stable short brand', () => {
  assert.equal(PRODUCT_NAME, '医数云策智慧医疗运营大数据与AI决策分析平台')
  assert.equal(PRODUCT_NAME, `${PRODUCT_SHORT_NAME}${PRODUCT_TAGLINE}`)
  assert.equal(INSIGHT_REPORT_TITLE, '医数云策洞察简报')
})

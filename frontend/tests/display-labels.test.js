import test from 'node:test'
import assert from 'node:assert/strict'

import {
  displayFieldLabel,
  displayMetricLabel,
  displayOptionLabel,
  displaySectionItemValue,
  displayText,
  displayValue,
  isNonDiseaseLabel,
  withoutNonDiseaseItems,
} from '../src/domain/displayLabels.js'
import {
  GENERATED_DIAGNOSIS_LABELS,
  GENERATED_HOSPITAL_LABELS,
} from '../src/domain/displayLabelsData.js'

test('display values use Chinese labels while preserving raw API values for context', () => {
  assert.equal(displayValue('70 or Older', 'age_group'), '70岁及以上')
  assert.equal(displayValue('Major', 'severity'), '重症')
  assert.equal(displayValue('Medical', 'medical_surgical'), '内科')
  assert.equal(displayValue('Surgical', 'medical_surgical'), '外科')
  assert.equal(displayValue('Not Applicable', 'medical_surgical'), '不适用')
  assert.equal(displayValue('Medicare', 'payment_type'), '联邦医疗保险')
  assert.equal(displayOptionLabel('gender', 'F'), '女性')
  assert.equal(displayOptionLabel('facility_id', 'OTHER'), '其他机构')
  assert.equal(displayOptionLabel('facility_id', "Blythedale Children's Hospital"), '布莱斯代尔儿童医院')
  assert.equal(displayOptionLabel('diagnosis_code', 'LEUKEMIA - ACUTE LYMPHOBLASTIC LEUKEMIA (ALL)'), '急性淋巴细胞白血病（ALL）')
  assert.equal(displayValue('Mount Sinai Hospital', 'hospital_top10'), '西奈山医院')
  assert.equal(displayValue('CARDIAC CATHETERIZATION', 'procedure'), '心导管检查')
  assert.equal(displayValue('MECHANICAL VENTILATION', 'procedures'), '机械通气')
  assert.equal(displayValue('ECHOCARDIOGRAM', 'procedure'), '超声心动图')
  assert.equal(displayValue('Home or Self Care', 'disposition'), '回家或自行照护')
  assert.equal(displayValue('Expired', 'disposition'), '死亡')
  assert.equal(displayOptionLabel('disposition', 'Left Against Medical Advice'), '未经医嘱离院')
})

test('field and metric labels cover raw English contract names', () => {
  assert.equal(displayFieldLabel('Total Charges'), '收费')
  assert.equal(displayFieldLabel('APR Severity of Illness Description'), '病情严重程度')
  assert.equal(displayMetricLabel({ key: 'avg_charges', label: 'Average Total Charges' }), '平均收费')
  assert.equal(displayMetricLabel({ key: 'accuracy', label: 'Accuracy' }), '准确率')
  assert.equal(displayFieldLabel('PRECISION'), '精确率')
  assert.equal(displayFieldLabel('facility_name'), '医院名称')
  assert.equal(displayFieldLabel('Facility Name'), '医院名称')
  assert.equal(displayFieldLabel('hospital_name'), '医院名称')
  assert.equal(displayFieldLabel('Hospital Name'), '医院名称')
  assert.equal(displayFieldLabel('disease_name'), '疾病名称')
  assert.equal(displayFieldLabel('disease_code'), '疾病编码')
  assert.equal(displayFieldLabel('facility_a'), '医院 A')
})

test('all current disease and hospital options have Chinese display labels', () => {
  for (const source of Object.keys(GENERATED_DIAGNOSIS_LABELS)) {
    const label = displayValue(source, 'diagnosis_code')
    assert.match(label, /[\u3400-\u9fff]/)
    assert.notEqual(label, source)
  }
  for (const source of Object.keys(GENERATED_HOSPITAL_LABELS)) {
    const label = displayValue(source, 'facility_name')
    assert.match(label, /[\u3400-\u9fff]/)
    assert.notEqual(label, source)
  }
})

test('section-aware labels translate chart categories and narrative text', () => {
  const paymentSection = { key: 'payment', title: '主支付方式结构' }
  const riskSection = { key: 'age_severity_matrix', title: '年龄组与病情严重程度结构' }
  const diagnosisSection = { key: 'diagnosis_charges', title: '按疾病比较：平均收费' }
  const hospitalSection = { key: 'facility_charges', title: '按医院比较：平均收费' }
  assert.equal(displaySectionItemValue('Private Health Insurance', paymentSection), '商业医疗保险')
  assert.equal(displaySectionItemValue('50 to 69', riskSection, 'x_label'), '50—69岁')
  assert.equal(displaySectionItemValue('Extreme', riskSection, 'y_label'), '极重症')
  assert.equal(displaySectionItemValue('Medical', { key: 'medical_surgical', title: '内外科结构' }), '内科')
  assert.equal(displaySectionItemValue('Surgical', { key: 'medical_surgical', title: '内外科结构' }), '外科')
  assert.equal(displaySectionItemValue('Not Applicable', { key: 'medical_surgical', title: '内外科结构' }), '不适用')
  assert.equal(displaySectionItemValue('RESPIRATORY DISTRESS SYNDROME', diagnosisSection), '呼吸窘迫综合征')
  assert.equal(displaySectionItemValue('CEREBRAL INFARCTION', diagnosisSection), '脑梗死')
  assert.equal(displaySectionItemValue('SECONDARY MALIGNANCIES', diagnosisSection), '继发性恶性肿瘤')
  assert.equal(displaySectionItemValue('Westchester Medical Center', hospitalSection), '威彻斯特医疗中心')
  assert.equal(displaySectionItemValue('CHEST RADIOGRAPHY', { key: 'procedures', title: '常见操作' }), '胸部X线检查')
  assert.equal(displaySectionItemValue('COMPUTED TOMOGRAPHY', { key: 'procedures', title: '常见操作' }), '计算机断层扫描')
  assert.equal(displaySectionItemValue('Skilled Nursing Home', { key: 'disposition', title: '高风险记录离院去向' }), '专业护理机构')
  assert.equal(displayFieldLabel('Patient Disposition'), '离院去向')
  assert.equal(displayText('Major/Extreme · Pearson'), '重症/极重症 · 皮尔逊')
  assert.equal(displayText('Mount Sinai Hospital'), '西奈山医院')
  assert.equal(displayText('New York-Presbyterian Hospital - New York Weill Cornell Center'), '纽约长老会医院—威尔康奈尔医疗中心')
})

test('disease sections exclude liveborn birth records from disease rankings', () => {
  assert.equal(isNonDiseaseLabel('LIVEBORN'), true)
  assert.equal(isNonDiseaseLabel(' liveborn '), true)
  assert.equal(isNonDiseaseLabel('活产儿'), true)
  assert.equal(isNonDiseaseLabel('SEPTICEMIA'), false)
  const section = {
    key: 'disease_top10',
    title: '疾病病例量 TOP10',
    items: [
      { name: 'LIVEBORN', value: 199014 },
      { name: 'SEPTICEMIA', value: 138035 },
    ],
  }
  const visible = withoutNonDiseaseItems(section)
  assert.deepEqual(visible.items, [{ name: 'SEPTICEMIA', value: 138035 }])
  assert.equal(visible.title, '疾病病例量排行')
})

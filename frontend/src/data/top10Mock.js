// Mock 只用于页面状态联调，不代表真实全量 SPARCS 结果。
const successItems = [
  { rank: 1, diagnosis_name: 'COMPLICATION OF OTHER SURGICAL OR MEDICAL CARE, INJURY, INITIAL ENCOUNTER', case_count: 2 },
  { rank: 2, diagnosis_name: 'LIVEBORN', case_count: 2 },
  { rank: 3, diagnosis_name: 'TRAUMATIC BRAIN INJURY (TBI); CONCUSSION, INITIAL ENCOUNTER', case_count: 2 },
  { rank: 4, diagnosis_name: 'ACUTE MYOCARDIAL INFARCTION', case_count: 1 },
  { rank: 5, diagnosis_name: 'ASTHMA', case_count: 1 },
  { rank: 6, diagnosis_name: 'CORONAVIRUS DISEASE 2019 (COVID-19)', case_count: 1 },
  { rank: 7, diagnosis_name: 'DIABETES MELLITUS WITH COMPLICATION', case_count: 1 },
  { rank: 8, diagnosis_name: 'MULTIPLE SCLEROSIS', case_count: 1 },
  { rank: 9, diagnosis_name: 'NONINFECTIOUS GASTROENTERITIS', case_count: 1 },
  { rank: 10, diagnosis_name: 'PARALYSIS (OTHER THAN CEREBRAL PALSY)', case_count: 1 },
]

const baseData = {
  metric: 'disease_case_count_top10',
  unit: 'discharge_records',
  generated_at: '2026-08-17T00:00:00.000000Z',
}

export const top10MockResponses = {
  success: {
    code: 'OK',
    message: 'success',
    data: {
      ...baseData,
      data_version: 'fixture:sparcs_mvp_sample:v1',
      items: successItems,
    },
    trace_id: '00000000-0000-4000-8000-000000000001',
  },
  empty: {
    code: 'OK',
    message: 'success',
    data: {
      ...baseData,
      data_version: 'fixture:sparcs_mvp_empty:v1',
      items: [],
    },
    trace_id: '00000000-0000-4000-8000-000000000002',
  },
}

export const top10MockData = top10MockResponses.success.data.items

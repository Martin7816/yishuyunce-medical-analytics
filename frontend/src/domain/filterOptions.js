function optionLabels(item) {
  if (item == null) return []
  const option = typeof item === 'object' ? item : { value: item, label: item }
  return [option.rawLabel, option.label, option.value]
    .filter(value => value != null)
    .map(value => String(value).trim())
    .filter(Boolean)
}

function sectionItemLabel(item) {
  if (item == null || typeof item !== 'object') return item
  return item.name ?? item.diagnosis_name ?? item.label
}

/**
 * Resolve published section items to existing filter options without inventing
 * values. The section order is retained so the result can be rendered as a
 * quick-filter group.
 */
export function optionsForSection(values = [], payload, sectionKey) {
  const items = payload?.sections?.find(section => section.key === sectionKey)?.items
  if (!Array.isArray(items) || !items.length || !Array.isArray(values)) return []

  const optionsByKey = new Map()
  for (const option of values) {
    for (const key of optionLabels(option)) {
      if (!optionsByKey.has(key)) optionsByKey.set(key, option)
    }
  }

  const seen = new Set()
  return items.map(item => {
    const key = String(sectionItemLabel(item) ?? '').trim()
    const option = optionsByKey.get(key)
    if (!option || seen.has(option.value)) return null
    seen.add(option.value)
    return option
  }).filter(Boolean)
}

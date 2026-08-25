function sameQuery(left, right) {
  return JSON.stringify(left) === JSON.stringify(right)
}

export function queryForFilters(config, values, routeQuery = {}) {
  const query = {}
  for (const filter of config.filters || []) {
    const value = values[filter.key]
    if (value !== '' && value != null) query[filter.key] = value
  }
  if (config.stage && routeQuery.mode === 'screen') query.mode = 'screen'
  return query
}

export function prepareFilterNavigation(values, config, key, value, routeQuery = {}) {
  const nextValues = { ...values, [key]: value }
  if (config.mutuallyExclusive?.includes(key) && value) {
    for (const other of config.mutuallyExclusive) {
      if (other !== key) nextValues[other] = ''
    }
  }

  const query = queryForFilters(config, nextValues, routeQuery)
  return {
    values: nextValues,
    query,
    shouldLoad: !sameQuery(query, routeQuery),
  }
}

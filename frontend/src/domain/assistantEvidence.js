export function hasAggregateEvidence(metrics, sectionKeys) {
  const metricCount = Array.isArray(metrics) ? metrics.length : 0
  const sectionCount = Array.isArray(sectionKeys) ? sectionKeys.length : 0
  return metricCount > 0 || sectionCount > 0
}

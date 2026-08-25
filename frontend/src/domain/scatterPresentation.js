export function scatterLegendLayout(innerWidth, groupCount) {
  const width = Math.max(0, Number(innerWidth) || 0)
  const count = Math.max(1, Number(groupCount) || 1)
  const columns = Math.min(count, width < 360 ? 3 : 5)
  const rows = Math.ceil(count / columns)
  return {
    columns,
    rows,
    cellWidth: width / columns,
    top: 34 + (rows - 1) * 18,
  }
}

export function scatterPointRadius(size, maxSize) {
  const value = Math.max(0, Number(size) || 0)
  const maximum = Math.max(1, Number(maxSize) || 1)
  return 4.5 + Math.sqrt(Math.min(1, value / maximum)) * 7
}

export function scatterPointOffset(groupIndex, groupCount) {
  const count = Math.max(1, Number(groupCount) || 1)
  const index = Math.min(count - 1, Math.max(0, Number(groupIndex) || 0))
  const step = Math.min(8, 24 / count)
  return (index - (count - 1) / 2) * step
}

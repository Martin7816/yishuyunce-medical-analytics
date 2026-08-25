export function shouldShowSection(section = {}, filters = {}) {
  // Once an age group is selected, the age distribution only repeats the active filter.
  return !(filters.age_group && section.key === 'age')
}

export function filterSectionsByActiveFilters(sections = [], filters = {}) {
  return sections.filter(section => shouldShowSection(section, filters))
}

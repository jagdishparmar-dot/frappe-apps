/** Build `{ label, value }[]` for FormControl type="select". */
export function selectOptions(values, { emptyLabel } = {}) {
  const options = (values || []).map((value) => ({
    label: String(value),
    value,
  }))
  if (emptyLabel !== undefined) {
    options.unshift({ label: emptyLabel, value: '' })
  }
  return options
}

export function selectOptionsFromRows(rows, labelKey, valueKey, { emptyLabel } = {}) {
  const options = (rows || []).map((row) => ({
    label: row[labelKey],
    value: row[valueKey],
  }))
  if (emptyLabel !== undefined) {
    options.unshift({ label: emptyLabel, value: '' })
  }
  return options
}

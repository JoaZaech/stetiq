import { describe, expect, it } from 'vitest'
import { readDataTableParams, writeDataTableParams, type DataTableParamsOptions } from './data-table-params'

const CLASSES: DataTableParamsOptions = {
  key: 'classes',
  filters: { label: 'text', parent: 'values', deprecated: 'toggle' },
  optional: ['deprecated'],
  search: 'q',
}

describe('readDataTableParams', () => {
  it('reads sort, filters, search and shown columns from the table’s own params', () => {
    const params = new URLSearchParams(
      'q=tick&classes.sort=-attributes&classes.sort=label&classes.f.label=cust' +
        '&classes.f.parent=Party&classes.f.parent=Agent&classes.f.deprecated=1&classes.col=deprecated' +
        '&relations.sort=label',
    )

    expect(readDataTableParams(params, CLASSES)).toEqual({
      sorting: [
        { id: 'attributes', desc: true },
        { id: 'label', desc: false },
      ],
      columnFilters: [
        { id: 'label', value: 'cust' },
        { id: 'parent', value: ['Party', 'Agent'] },
        { id: 'deprecated', value: true },
      ],
      globalFilter: 'tick',
      columnVisibility: { deprecated: true },
    })
  })

  it('has no sort, filter or search, and hides optional columns, when the URL says nothing', () => {
    expect(readDataTableParams(new URLSearchParams('classes.f.unknown=x'), CLASSES)).toEqual({
      sorting: [],
      columnFilters: [],
      globalFilter: '',
      columnVisibility: { deprecated: false },
    })
  })

  it('keeps its search under its own key unless told to share one', () => {
    const own = { key: 'classes', filters: {} }
    expect(readDataTableParams(new URLSearchParams('q=a&classes.q=b'), own).globalFilter).toBe('b')
  })
})

describe('writeDataTableParams', () => {
  it('round-trips through read, leaving other params alone', () => {
    const state = {
      sorting: [{ id: 'label', desc: true }],
      columnFilters: [
        { id: 'parent', value: ['Party'] },
        { id: 'deprecated', value: true },
      ],
      globalFilter: 'tick',
      columnVisibility: { deprecated: true },
    }
    const params = new URLSearchParams('view=table&classes.sort=parent&relations.sort=label')

    writeDataTableParams(params, CLASSES, state)

    expect(readDataTableParams(params, CLASSES)).toEqual(state)
    expect(params.get('view')).toBe('table')
    expect(params.get('relations.sort')).toBe('label')
    expect(params.getAll('classes.sort')).toEqual(['-label'])
  })

  it('drops the table’s params once nothing is sorted, filtered, searched or shown', () => {
    const params = new URLSearchParams('q=x&classes.sort=label&classes.f.label=a&classes.col=deprecated')

    writeDataTableParams(params, CLASSES, {
      sorting: [],
      columnFilters: [],
      globalFilter: '',
      columnVisibility: { deprecated: false },
    })

    expect(params.toString()).toBe('')
  })
})

describe('grouping', () => {
  const ATTRIBUTES: DataTableParamsOptions = { key: 'attributes', filters: {}, grouping: ['owner', 'type'] }

  it('groups by the first groupable column unless the URL picks another or none', () => {
    const grouping = (query: string) => readDataTableParams(new URLSearchParams(query), ATTRIBUTES).grouping

    expect(grouping('')).toEqual(['owner'])
    expect(grouping('attributes.group=type')).toEqual(['type'])
    expect(grouping('attributes.group=none')).toEqual([])
    expect(grouping('attributes.group=description')).toEqual(['owner'])
  })

  it('writes only a grouping other than the default', () => {
    const write = (grouping: string[]) => {
      const params = new URLSearchParams('attributes.group=type')
      writeDataTableParams(params, ATTRIBUTES, { ...readDataTableParams(params, ATTRIBUTES), grouping })
      return params.toString()
    }

    expect(write(['owner'])).toBe('')
    expect(write(['type'])).toBe('attributes.group=type')
    expect(write([])).toBe('attributes.group=none')
  })

  it('leaves grouping out of a table without groupable columns', () => {
    expect(readDataTableParams(new URLSearchParams('classes.group=label'), CLASSES)).not.toHaveProperty('grouping')
  })
})

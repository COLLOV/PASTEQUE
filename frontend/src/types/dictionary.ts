export interface DictionaryColumn {
  name: string
  description?: string
  type?: string
  synonyms?: string[]
  unit?: string
  example?: string
  pii?: boolean
  nullable?: boolean
  enum?: string[]
}

export interface DictionaryTable {
  table: string
  title?: string
  description?: string
  columns: DictionaryColumn[]
}

export interface DictionaryTableSummary {
  table: string
  has_dictionary: boolean
  columns_count: number
}

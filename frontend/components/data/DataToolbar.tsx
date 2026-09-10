"use client";

import { Button, Input, Select } from "antd";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";

import type { FilterValues } from "@/hooks/usePagedList";

export type SelectFilter = {
  key: string;
  placeholder: string;
  options: Array<{ value: string; label: string }>;
};

type Props = {
  keyword: string;
  onKeywordChange: (value: string) => void;
  searchPlaceholder?: string;
  filters?: SelectFilter[];
  filterValues?: FilterValues;
  onFilterChange?: (key: string, value: string | undefined) => void;
  sortOptions?: Array<{ value: string; label: string }>;
  sort?: string;
  onSortChange?: (value: string | undefined) => void;
  onReset: () => void;
  /** Shown on the right, e.g. "共 12 条". */
  summary?: string;
  showReset?: boolean;
};

export function DataToolbar({
  keyword,
  onKeywordChange,
  searchPlaceholder = "搜索关键词",
  filters = [],
  filterValues = {},
  onFilterChange,
  sortOptions,
  sort,
  onSortChange,
  onReset,
  summary,
  showReset = true,
}: Props) {
  return (
    <div className="data-toolbar">
      <div className="data-toolbar__fields">
        <Input
          className="data-toolbar__field data-toolbar__search"
          allowClear
          value={keyword}
          prefix={<SearchOutlined />}
          placeholder={searchPlaceholder}
          onChange={(event) => onKeywordChange(event.target.value)}
        />

        {filters.map((filter) => (
          <Select
            key={filter.key}
            className="data-toolbar__field data-toolbar__select"
            allowClear
            value={filterValues[filter.key] ?? undefined}
            placeholder={filter.placeholder}
            options={filter.options}
            onChange={(value) => onFilterChange?.(filter.key, value ?? undefined)}
          />
        ))}

        {sortOptions && sortOptions.length > 0 ? (
          <Select
            className="data-toolbar__field data-toolbar__select data-toolbar__select--sort"
            value={sort}
            placeholder="排序"
            options={sortOptions}
            onChange={(value) => onSortChange?.(value ?? undefined)}
          />
        ) : null}
      </div>

      <div className="data-toolbar__actions">
        {summary ? <span className="data-toolbar__summary">{summary}</span> : null}
        {showReset ? (
          <Button icon={<ReloadOutlined />} onClick={onReset}>
            重置
          </Button>
        ) : null}
      </div>
    </div>
  );
}

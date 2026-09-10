"use client";

import { useCallback, useMemo, useState } from "react";

export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export type FilterValues = Record<string, string | undefined>;

/** Stable defaults; inline `{}` literals would invalidate the memo every render. */
const NO_MATCHERS: Record<string, never> = {};
const NO_COMPARATORS: Record<string, never> = {};

type Options<T> = {
  items: T[];
  /** Fields matched against the keyword, case-insensitively. */
  searchFields: (item: T) => Array<string | null | undefined>;
  /** Predicate per filter key; only called when that filter has a value. */
  filterMatchers?: Record<string, (item: T, value: string) => boolean>;
  comparators?: Record<string, (a: T, b: T) => number>;
  defaultSort?: string;
  defaultPageSize?: number;
};

type Result<T> = {
  keyword: string;
  setKeyword: (value: string) => void;
  filters: FilterValues;
  setFilter: (key: string, value: string | undefined) => void;
  sort: string | undefined;
  setSort: (value: string | undefined) => void;
  reset: () => void;
  page: number;
  setPage: (page: number) => void;
  pageSize: number;
  setPageSize: (size: number) => void;
  /** Items after search + filter + sort, before pagination. */
  filtered: T[];
  /** The current page's slice. */
  paged: T[];
  total: number;
  isFiltered: boolean;
};

/**
 * Client-side search, filter, sort and pagination.
 *
 * The list endpoints return full arrays with no page parameters, so slicing
 * happens here. The controlled surface matches what a server-paged version
 * would expose, so swapping in a paged endpoint later is a local change.
 */
export function usePagedList<T>({
  items,
  searchFields,
  filterMatchers = NO_MATCHERS,
  comparators = NO_COMPARATORS,
  defaultSort,
  defaultPageSize = 20,
}: Options<T>): Result<T> {
  const [keyword, setKeywordRaw] = useState("");
  const [filters, setFilters] = useState<FilterValues>({});
  const [sort, setSortRaw] = useState<string | undefined>(defaultSort);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSizeRaw] = useState(defaultPageSize);

  // Any narrowing of the result set must return to the first page, otherwise
  // the user lands on an out-of-range page showing nothing.
  const setKeyword = useCallback((value: string) => {
    setKeywordRaw(value);
    setPage(1);
  }, []);

  const setFilter = useCallback((key: string, value: string | undefined) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  }, []);

  const setSort = useCallback((value: string | undefined) => {
    setSortRaw(value);
    setPage(1);
  }, []);

  const setPageSize = useCallback((size: number) => {
    setPageSizeRaw(size);
    setPage(1);
  }, []);

  const reset = useCallback(() => {
    setKeywordRaw("");
    setFilters({});
    setSortRaw(defaultSort);
    setPage(1);
  }, [defaultSort]);

  const filtered = useMemo(() => {
    const needle = keyword.trim().toLowerCase();

    let result = items.filter((item) => {
      if (needle) {
        const haystack = searchFields(item)
          .filter((value): value is string => Boolean(value))
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(needle)) return false;
      }

      for (const [key, value] of Object.entries(filters)) {
        if (!value) continue;
        const matcher = filterMatchers[key];
        if (matcher && !matcher(item, value)) return false;
      }

      return true;
    });

    const comparator = sort ? comparators[sort] : undefined;
    if (comparator) {
      result = [...result].sort(comparator);
    }

    return result;
  }, [comparators, filterMatchers, filters, items, keyword, searchFields, sort]);

  /*
   * `page` can fall out of range when `items` shrinks underneath us (a reload
   * returning fewer rows). Clamping on read rather than in an effect keeps the
   * slice non-empty without an extra render pass.
   */
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount);

  const paged = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, safePage, pageSize]);

  const isFiltered = Boolean(keyword.trim()) || Object.values(filters).some(Boolean);

  return {
    keyword,
    setKeyword,
    filters,
    setFilter,
    sort,
    setSort,
    reset,
    page: safePage,
    setPage,
    pageSize,
    setPageSize,
    filtered,
    paged,
    total: filtered.length,
    isFiltered,
  };
}

"use client";

import { useCallback, useEffect, useState } from "react";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppPagination } from "@/components/data/AppPagination";
import { DataToolbar } from "@/components/data/DataToolbar";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { TASK_STATUS_OPTIONS } from "@/components/project/StatusTags";
import { TaskCard } from "@/components/ui/TaskCard";
import { PAGE_SIZE_OPTIONS, type FilterValues } from "@/hooks/usePagedList";
import { fetchMyTasks } from "@/services/tasks";
import type { Task } from "@/types/task";

const FILTERS = [{ key: "status", placeholder: "状态", options: TASK_STATUS_OPTIONS }];

const SORT_OPTIONS = [
  { value: "due", label: "按截止日期" },
  { value: "name", label: "按任务名称" },
  { value: "project", label: "按项目" },
];

function MyTasksPageInner() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [keyword, setKeyword] = useState("");
  const [debouncedKeyword, setDebouncedKeyword] = useState("");
  const [filters, setFilters] = useState<FilterValues>({});
  const [sort, setSort] = useState<string | undefined>("due");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedKeyword(keyword.trim()), 250);
    return () => window.clearTimeout(handle);
  }, [keyword]);

  useEffect(() => {
    setPage(1);
  }, [debouncedKeyword, filters.status, sort, pageSize]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchMyTasks({
      page,
      pageSize,
      status: filters.status,
      q: debouncedKeyword || undefined,
      sort: (sort as "due" | "name" | "project") || "due",
    })
      .then((data) => {
        if (cancelled) return;
        setTasks(data.items);
        setTotal(data.total);
        setFailed(false);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, pageSize, filters.status, debouncedKeyword, sort, reloadKey]);

  const retry = useCallback(() => {
    setFailed(false);
    setReloadKey((value) => value + 1);
  }, []);

  const reset = useCallback(() => {
    setKeyword("");
    setDebouncedKeyword("");
    setFilters({});
    setSort("due");
    setPage(1);
    setPageSize(20);
  }, []);

  const setFilter = useCallback((key: string, value: string | undefined) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }, []);

  const onPageSizeChange = useCallback((size: number) => {
    setPageSize(PAGE_SIZE_OPTIONS.includes(size) ? size : 20);
  }, []);

  const isFiltered = Boolean(debouncedKeyword || filters.status);

  return (
    <PageContainer>
      <PageHeader
        title="我的任务"
        subtitle="今天需要更新的任务会在这里显示，点击即可快速提交进展。"
      />

      {failed && !loading ? (
        <ErrorState description="无法获取任务列表，请稍后重试。" onRetry={retry} />
      ) : (
        <>
          <DataToolbar
            keyword={keyword}
            onKeywordChange={setKeyword}
            searchPlaceholder="搜索任务名称 / 项目"
            filters={FILTERS}
            filterValues={filters}
            onFilterChange={setFilter}
            sortOptions={SORT_OPTIONS}
            sort={sort}
            onSortChange={setSort}
            onReset={reset}
            summary={`共 ${total} 个任务`}
          />

          {loading ? (
            <LoadingState tip="加载任务…" />
          ) : total === 0 ? (
            <EmptyState
              title={isFiltered ? "没有符合条件的任务" : "暂无任务"}
              description={
                isFiltered
                  ? "试着调整搜索词或筛选条件。"
                  : "当前没有分配给你的任务。"
              }
            />
          ) : (
            <div className="card-grid">
              {tasks.map((task) => (
                <TaskCard key={task.id} task={task} />
              ))}
            </div>
          )}

          <AppPagination
            page={page}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
            onPageSizeChange={onPageSizeChange}
          />
        </>
      )}
    </PageContainer>
  );
}

export default function MyTasksPage() {
  return (
    <RequireAuth>
      <MyTasksPageInner />
    </RequireAuth>
  );
}

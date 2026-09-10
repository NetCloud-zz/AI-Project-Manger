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
import { usePagedList } from "@/hooks/usePagedList";
import { fetchMyTasks } from "@/services/tasks";
import type { Task } from "@/types/task";

const FILTERS = [{ key: "status", placeholder: "状态", options: TASK_STATUS_OPTIONS }];

const SORT_OPTIONS = [
  { value: "due", label: "按截止日期" },
  { value: "name", label: "按任务名称" },
  { value: "project", label: "按项目" },
];

const SEARCH_FIELDS = (item: Task) => [
  item.task_name,
  item.project?.project_code,
  item.project?.project_name,
];

const MATCHERS = {
  status: (item: Task, value: string) => item.status === value,
};

const COMPARATORS = {
  due: (a: Task, b: Task) => (a.due_date ?? "9999-12-31").localeCompare(b.due_date ?? "9999-12-31"),
  name: (a: Task, b: Task) => a.task_name.localeCompare(b.task_name),
  project: (a: Task, b: Task) =>
    (a.project?.project_code ?? "").localeCompare(b.project?.project_code ?? ""),
};

function MyTasksPageInner() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchMyTasks()
      .then((data) => {
        if (!cancelled) setTasks(data);
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
  }, [reloadKey]);

  const retry = useCallback(() => {
    setLoading(true);
    setFailed(false);
    setReloadKey((value) => value + 1);
  }, []);

  const list = usePagedList({
    items: tasks,
    searchFields: SEARCH_FIELDS,
    filterMatchers: MATCHERS,
    comparators: COMPARATORS,
    defaultSort: "due",
  });

  return (
    <PageContainer>
      <PageHeader
        title="我的任务"
        subtitle="今天需要更新的任务会在这里显示，点击即可快速提交进展。"
      />

      {loading ? (
        <LoadingState tip="加载任务…" />
      ) : failed ? (
        <ErrorState description="无法获取任务列表，请稍后重试。" onRetry={retry} />
      ) : tasks.length === 0 ? (
        <EmptyState title="暂无任务" description="当前没有分配给你的任务。" />
      ) : (
        <>
          <DataToolbar
            keyword={list.keyword}
            onKeywordChange={list.setKeyword}
            searchPlaceholder="搜索任务名称 / 项目"
            filters={FILTERS}
            filterValues={list.filters}
            onFilterChange={list.setFilter}
            sortOptions={SORT_OPTIONS}
            sort={list.sort}
            onSortChange={list.setSort}
            onReset={list.reset}
            summary={`共 ${list.total} 个任务`}
          />

          {list.total === 0 ? (
            <EmptyState title="没有符合条件的任务" description="试着调整搜索词或筛选条件。" />
          ) : (
            <div className="card-grid">
              {list.paged.map((task) => (
                <TaskCard key={task.id} task={task} />
              ))}
            </div>
          )}

          <AppPagination
            page={list.page}
            pageSize={list.pageSize}
            total={list.total}
            onPageChange={list.setPage}
            onPageSizeChange={list.setPageSize}
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

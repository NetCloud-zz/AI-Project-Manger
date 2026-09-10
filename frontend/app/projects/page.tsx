"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "antd";
import { PlusOutlined } from "@ant-design/icons";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppPagination } from "@/components/data/AppPagination";
import { DataToolbar } from "@/components/data/DataToolbar";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { PROJECT_STATUS_OPTIONS, RISK_OPTIONS } from "@/components/project/StatusTags";
import { useAuth } from "@/components/providers/AuthProvider";
import { ProjectCard } from "@/components/ui/ProjectCard";
import { usePagedList } from "@/hooks/usePagedList";
import { fetchProjects } from "@/services/projects";
import type { Project } from "@/types/project";

const FILTERS = [
  { key: "status", placeholder: "状态", options: PROJECT_STATUS_OPTIONS },
  { key: "risk_level", placeholder: "风险", options: RISK_OPTIONS },
];

const SORT_OPTIONS = [
  { value: "code", label: "按项目编号" },
  { value: "deadline", label: "按目标日期" },
  { value: "risk", label: "按风险等级" },
];

const RISK_WEIGHT: Record<string, number> = { DELAYED: 0, AT_RISK: 1, NORMAL: 2 };

const SEARCH_FIELDS = (item: Project) => [
  item.project_code,
  item.project_name,
  item.goal,
  item.owner?.name,
];

const MATCHERS = {
  status: (item: Project, value: string) => item.status === value,
  risk_level: (item: Project, value: string) => item.risk_level === value,
};

const COMPARATORS = {
  code: (a: Project, b: Project) => a.project_code.localeCompare(b.project_code),
  deadline: (a: Project, b: Project) =>
    (a.target_date ?? "9999").localeCompare(b.target_date ?? "9999"),
  risk: (a: Project, b: Project) =>
    (RISK_WEIGHT[a.risk_level] ?? 9) - (RISK_WEIGHT[b.risk_level] ?? 9),
};

function ProjectsPageInner() {
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchProjects()
      .then((data) => {
        if (!cancelled) setProjects(data);
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
    items: projects,
    searchFields: SEARCH_FIELDS,
    filterMatchers: MATCHERS,
    comparators: COMPARATORS,
    defaultSort: "code",
  });

  const canCreate = user?.role === "ADMIN" || user?.role === "PROJECT_OWNER";

  const action = useMemo(
    () =>
      canCreate ? (
        <Link href="/projects/new">
          <Button type="primary" icon={<PlusOutlined />}>
            新建项目
          </Button>
        </Link>
      ) : undefined,
    [canCreate],
  );

  return (
    <PageContainer>
      <PageHeader
        title="项目"
        subtitle="查看所有研发项目的状态与风险。"
        action={action}
      />

      {loading ? (
        <LoadingState tip="加载项目…" />
      ) : failed ? (
        <ErrorState description="无法获取项目列表，请稍后重试。" onRetry={retry} />
      ) : projects.length === 0 ? (
        <EmptyState
          title="暂无项目"
          description={canCreate ? "创建第一个项目开始跟踪研发进度。" : undefined}
          action={action}
        />
      ) : (
        <>
          <DataToolbar
            keyword={list.keyword}
            onKeywordChange={list.setKeyword}
            searchPlaceholder="搜索项目编号 / 名称 / 负责人"
            filters={FILTERS}
            filterValues={list.filters}
            onFilterChange={list.setFilter}
            sortOptions={SORT_OPTIONS}
            sort={list.sort}
            onSortChange={list.setSort}
            onReset={list.reset}
            summary={`共 ${list.total} 个项目`}
          />

          {list.total === 0 ? (
            <EmptyState title="没有符合条件的项目" description="试着调整搜索词或筛选条件。" />
          ) : (
            <div className="card-grid">
              {list.paged.map((item) => (
                <ProjectCard key={item.id} project={item} />
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

export default function ProjectsPage() {
  return (
    <RequireAuth>
      <ProjectsPageInner />
    </RequireAuth>
  );
}

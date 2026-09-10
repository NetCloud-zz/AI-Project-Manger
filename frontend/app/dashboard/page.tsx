"use client";

import { useCallback, useEffect, useState } from "react";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { SectionTitle } from "@/components/common/SectionTitle";
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
import { StatTile } from "@/components/ui/StatTile";
import { usePagedList } from "@/hooks/usePagedList";
import { fetchDashboard } from "@/services/dashboard";
import {
  isManagementDashboard,
  type DashboardProjectItem,
  type DashboardData,
  type ManagementDashboard,
  type PersonalDashboard,
} from "@/types/dashboard";

const FILTERS = [
  { key: "status", placeholder: "状态", options: PROJECT_STATUS_OPTIONS },
  { key: "risk_level", placeholder: "风险", options: RISK_OPTIONS },
];

const SORT_OPTIONS = [
  { value: "risk", label: "按风险等级" },
  { value: "code", label: "按项目编号" },
  { value: "deadline", label: "按下一节点" },
];

const RISK_WEIGHT: Record<string, number> = { DELAYED: 0, AT_RISK: 1, NORMAL: 2 };

const SEARCH_FIELDS = (item: DashboardProjectItem) => [
  item.project_code,
  item.project_name,
  item.owner,
  item.current_focus,
];

const MATCHERS = {
  status: (item: DashboardProjectItem, value: string) => item.status === value,
  risk_level: (item: DashboardProjectItem, value: string) => item.risk_level === value,
};

const COMPARATORS = {
  risk: (a: DashboardProjectItem, b: DashboardProjectItem) =>
    (RISK_WEIGHT[a.risk_level] ?? 9) - (RISK_WEIGHT[b.risk_level] ?? 9),
  code: (a: DashboardProjectItem, b: DashboardProjectItem) =>
    a.project_code.localeCompare(b.project_code),
  deadline: (a: DashboardProjectItem, b: DashboardProjectItem) =>
    (a.next_deadline ?? "9999").localeCompare(b.next_deadline ?? "9999"),
};

function ManagementDashboardView({ data }: { data: ManagementDashboard }) {
  const list = usePagedList({
    items: data.project_items,
    searchFields: SEARCH_FIELDS,
    filterMatchers: MATCHERS,
    comparators: COMPARATORS,
    defaultSort: "risk",
  });

  return (
    <>
      <div className="stat-grid stat-grid--5">
        <StatTile label="项目总数" value={data.project_total} />
        <StatTile label="需关注" value={data.management_attention_count} tone="danger" />
        <StatTile label="正常" value={data.normal_count} tone="success" />
        <StatTile label="风险" value={data.at_risk_count} tone="warning" />
        <StatTile label="延期" value={data.delayed_count} tone="danger" />
      </div>

      <SectionTitle>项目列表</SectionTitle>

      {data.project_items.length === 0 ? (
        <EmptyState title="暂无项目" />
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
                <ProjectCard key={item.project_id} project={item} />
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
    </>
  );
}

function PersonalDashboardView({ data }: { data: PersonalDashboard }) {
  return (
    <div className="stat-grid stat-grid--2">
      <StatTile label="进行中任务" value={data.my_active_tasks} />
      <StatTile label="已逾期" value={data.my_overdue_tasks} tone="danger" />
    </div>
  );
}

function DashboardPageInner() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const isManager =
    user?.role === "ADMIN" || user?.role === "EXECUTIVE" || user?.role === "PROJECT_OWNER";

  useEffect(() => {
    let cancelled = false;
    fetchDashboard()
      .then((result) => {
        if (!cancelled) setData(result);
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

  return (
    <PageContainer>
      <PageHeader
        title={isManager ? "管理看板" : "我的工作台"}
        subtitle={isManager ? "快速掌握项目整体状态与需关注事项。" : "查看您当前的任务概况。"}
      />

      {loading ? (
        <LoadingState tip="加载看板…" />
      ) : failed || !data ? (
        <ErrorState description="无法获取看板数据，请稍后重试。" onRetry={retry} />
      ) : isManagementDashboard(data) ? (
        <ManagementDashboardView data={data} />
      ) : (
        <PersonalDashboardView data={data} />
      )}
    </PageContainer>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardPageInner />
    </RequireAuth>
  );
}

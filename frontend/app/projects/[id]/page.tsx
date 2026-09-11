"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { App, AutoComplete, Button, DatePicker, Form, Input, InputNumber, Segmented, Space } from "antd";
import { BarChartOutlined, PlusOutlined, UnorderedListOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppCard } from "@/components/common/AppCard";
import { SectionTitle } from "@/components/common/SectionTitle";
import { AppPagination } from "@/components/data/AppPagination";
import { DataToolbar } from "@/components/data/DataToolbar";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { ProjectGanttPanel } from "@/components/gantt/ProjectGanttPanel";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { ActionItemsPanel } from "@/components/project/ActionItemsPanel";
import { ProjectIssuesPanel } from "@/components/project/ProjectIssuesPanel";
import { ProjectForecastCard } from "@/components/project/ProjectForecastCard";
import { ProjectManagePanel } from "@/components/project/ProjectManagePanel";
import { ProjectStatusTag, RiskTag } from "@/components/project/StatusTags";
import { useAuth } from "@/components/providers/AuthProvider";
import { TaskCard } from "@/components/ui/TaskCard";
import { usePagedList } from "@/hooks/usePagedList";
import { fetchProjectActionItems } from "@/services/action_items";
import { createProjectTask, fetchProject, fetchProjectTasks } from "@/services/projects";
import { fetchProjectRecentProgress } from "@/services/progress";
import { fetchProjectOpenIssues } from "@/services/issues";
import { fetchLatestProjectSummary, regenerateProjectSummary } from "@/services/summaries";
import { fetchAIRun } from "@/services/ai_runs";
import type { ActionItem } from "@/types/action_item";
import type { Project } from "@/types/project";
import type { Task } from "@/types/task";
import type { RecentProgressItem } from "@/types/progress";
import type { Issue } from "@/types/issue";
import type { DailyProjectSummary } from "@/types/daily_summary";

function ProjectDetailInner() {
  const params = useParams<{ id: string }>();
  const projectId = Number(params.id);
  const { message } = App.useApp();
  const { user } = useAuth();
  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [recentProgress, setRecentProgress] = useState<RecentProgressItem[]>([]);
  const [openIssues, setOpenIssues] = useState<Issue[]>([]);
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [latestSummary, setLatestSummary] = useState<DailyProjectSummary | null>(null);
  const [summaryStatus, setSummaryStatus] = useState<string | null>(null);
  const [regenLoading, setRegenLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [taskView, setTaskView] = useState<"list" | "gantt">("list");

  const reloadTasks = useCallback(async () => {
    const next = await fetchProjectTasks(projectId);
    setTasks(next);
  }, [projectId]);

  const reloadActionItems = useCallback(async () => {
    setActionItems(await fetchProjectActionItems(projectId));
  }, [projectId]);

  const reloadOpenIssues = useCallback(async () => {
    setOpenIssues(await fetchProjectOpenIssues(projectId));
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchProject(projectId),
      fetchProjectTasks(projectId),
      fetchProjectRecentProgress(projectId),
      fetchProjectOpenIssues(projectId),
      fetchProjectActionItems(projectId),
      fetchLatestProjectSummary(projectId),
    ])
      .then(([p, t, rp, issues, items, summary]) => {
        if (!cancelled) {
          setProject(p);
          setTasks(t);
          setRecentProgress(rp);
          setOpenIssues(issues);
          setActionItems(items);
          setLatestSummary(summary);
        }
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
  }, [projectId, reloadKey]);

  const retry = useCallback(() => {
    setLoading(true);
    setFailed(false);
    setReloadKey((value) => value + 1);
  }, []);

  const isProjectOwner =
    Boolean(user) &&
    Boolean(project) &&
    (project!.owner_id === user!.id ||
      (project!.owners ?? []).some((owner) => owner.id === user!.id));
  const canManage = user?.role === "ADMIN" || (user?.role === "PROJECT_OWNER" && isProjectOwner);

  const activeTasks = tasks.filter((task) => task.is_active_branch !== false);
  const taskList = usePagedList({
    items: activeTasks,
    searchFields: (item) => [
      item.task_name,
      item.work_stream,
      item.branch_label,
      item.owner?.name,
      item.status,
    ],
    defaultPageSize: 10,
  });
  const progressList = usePagedList({
    items: recentProgress,
    searchFields: (item) => [item.task_name, item.user_name, item.raw_content, item.summary],
    defaultPageSize: 10,
  });

  const onRegenerateSummary = async () => {
    setRegenLoading(true);
    setSummaryStatus("QUEUED");
    try {
      const res = await regenerateProjectSummary(projectId);
      message.success("每日摘要生成中…");
      const started = Date.now();
      while (Date.now() - started < 120_000) {
        await new Promise((r) => setTimeout(r, 2500));
        const run = await fetchAIRun(res.ai_run_id);
        setSummaryStatus(run.status);
        if (
          run.status === "SUCCEEDED" ||
          run.status === "FAILED" ||
          run.status === "DISABLED"
        ) {
          if (run.status === "SUCCEEDED") {
            const next = await fetchLatestProjectSummary(projectId);
            setLatestSummary(next);
            message.success("每日摘要已更新");
          } else if (run.status === "DISABLED") {
            message.warning(run.user_message || "LLM 未启用");
          } else {
            message.error(run.user_message || "摘要生成失败");
          }
          break;
        }
      }
    } catch {
      message.error("重新生成失败");
      setSummaryStatus("FAILED");
    } finally {
      setRegenLoading(false);
    }
  };

  const onCreateTask = async (values: {
    task_name: string;
    work_stream?: string;
    owner_id?: number | null;
    date_range?: [dayjs.Dayjs, dayjs.Dayjs] | null;
  }) => {
    setSubmitting(true);
    try {
      const range = values.date_range;
      await createProjectTask(projectId, {
        task_name: values.task_name,
        work_stream: values.work_stream?.trim() || null,
        owner_id: values.owner_id ?? null,
        start_date: range?.[0]?.format("YYYY-MM-DD") ?? null,
        due_date: range?.[1]?.format("YYYY-MM-DD") ?? null,
      });
      message.success("任务已创建");
      setShowTaskForm(false);
      await reloadTasks();
    } catch {
      message.error("创建任务失败");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <PageContainer>
        <LoadingState tip="加载项目…" />
      </PageContainer>
    );
  }

  if (failed || !project) {
    return (
      <PageContainer>
        <ErrorState description="无法获取项目详情，请稍后重试。" onRetry={retry} />
      </PageContainer>
    );
  }

  // EXECUTIVE is read-only everywhere; everyone else who can open the project
  // may log problems and action items.
  const canContribute = Boolean(user && user.role !== "EXECUTIVE");
  const taskOptions = activeTasks.map((task) => ({ value: task.id, label: task.task_name }));
  const workStreamOptions = [
    ...new Set(activeTasks.map((task) => task.work_stream?.trim()).filter(Boolean)),
  ].map((value) => ({ value: value as string }));
  const issueOptions = openIssues.map((issue) => ({ value: issue.id, label: issue.title }));
  const ownerOptions = Array.from(
    new Map(
      [
        ...(project.owners ?? []).map((owner) => ({ id: owner.id, name: owner.name })),
        project.owner ? { id: project.owner.id, name: project.owner.name } : null,
        user ? { id: user.id, name: user.name } : null,
        ...tasks.map((task) =>
          task.owner ? { id: task.owner.id, name: task.owner.name } : null,
        ),
      ]
        .filter((entry): entry is { id: number; name: string } => entry != null)
        .map((entry) => [entry.id, { value: entry.id, label: entry.name }] as const),
    ).values(),
  );

  return (
    <PageContainer>
      <Space wrap>
        <Button href={`/projects/${projectId}/planning`}>计划资料与路线</Button>
        <Button href={`/projects/${projectId}/risks`}>风险与建议</Button>
      </Space>
      <PageHeader
        backHref="/projects"
        backLabel="项目列表"
        title={project.project_code}
        subtitle={project.project_name}
        action={
          canManage ? (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setShowTaskForm((value) => !value)}
            >
              {showTaskForm ? "取消" : "新建任务"}
            </Button>
          ) : undefined
        }
      />

      <AppCard stack="sm">
        {project.goal ? <p className="detail-text">{project.goal}</p> : null}
        <div className="chip-row chip-row--flush">
          <ProjectStatusTag status={project.status} />
          <RiskTag level={project.risk_level} />
        </div>
      </AppCard>

      <ProjectManagePanel
        project={project}
        canManage={Boolean(canManage)}
        onChanged={setProject}
      />

      <ProjectForecastCard
        projectId={projectId}
        visible={Boolean(canManage) || user?.role === "EXECUTIVE"}
      />

      {showTaskForm ? (
        <AppCard>
          <Form layout="vertical" onFinish={onCreateTask}>
            <Form.Item label="任务名称" name="task_name" rules={[{ required: true }]}>
              <Input placeholder="输入任务名称" />
            </Form.Item>
            <Form.Item
              label="所属工作流"
              name="work_stream"
              extra="甘特图按工作流分组，例如「设计」「开发」「测试」「上线」。留空则归入未分组。"
            >
              <AutoComplete
                options={workStreamOptions}
                placeholder="选择或输入工作流"
                filterOption={(input, option) =>
                  String(option?.value ?? "").toLowerCase().includes(input.toLowerCase())
                }
                allowClear
              />
            </Form.Item>
            <Form.Item
              label="负责人 ID"
              name="owner_id"
              extra="可选；可先创建任务，负责人后续再指派。"
            >
              <InputNumber className="full-width" min={1} placeholder="待定（可留空）" />
            </Form.Item>
            <Form.Item
              label="起止日期"
              name="date_range"
              extra="可选；二级阶段用上方「所属工作流」表示，三级执行任务也可先不设日期。"
            >
              <DatePicker.RangePicker className="full-width" allowEmpty={[true, true]} />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting}>
              保存任务
            </Button>
          </Form>
        </AppCard>
      ) : null}

      <div className="project-detail-layout">
        <div className="project-detail-layout__main">
          <SectionTitle
            extra={
              <Segmented
                value={taskView}
                onChange={(value) => setTaskView(value as "list" | "gantt")}
                options={[
                  { value: "list", icon: <UnorderedListOutlined />, title: "列表" },
                  { value: "gantt", icon: <BarChartOutlined />, title: "甘特图" },
                ]}
              />
            }
          >
            任务
          </SectionTitle>

          {taskView === "gantt" ? (
            <ProjectGanttPanel projectId={projectId} />
          ) : activeTasks.length === 0 ? (
            <EmptyState title="暂无任务" description="创建任务以开始跟踪进度。" />
          ) : (
            <>
              <DataToolbar
                keyword={taskList.keyword}
                onKeywordChange={taskList.setKeyword}
                searchPlaceholder="搜索任务 / 工作流 / 负责人"
                onReset={taskList.reset}
                summary={`共 ${taskList.total} 条`}
              />
              {taskList.paged.length === 0 ? (
                <EmptyState title="无匹配结果" description="试试调整关键词。" />
              ) : (
                <div className="card-grid">
                  {taskList.paged.map((task) => (
                    <TaskCard key={task.id} task={task} showUpdateButton={false} />
                  ))}
                </div>
              )}
              <AppPagination
                page={taskList.page}
                pageSize={taskList.pageSize}
                total={taskList.total}
                onPageChange={taskList.setPage}
                onPageSizeChange={taskList.setPageSize}
              />
            </>
          )}

          <ActionItemsPanel
            projectId={projectId}
            items={actionItems}
            canManageAll={Boolean(canManage)}
            canCreate={canContribute}
            currentUserId={user?.id}
            ownerOptions={ownerOptions}
            taskOptions={taskOptions}
            issueOptions={issueOptions}
            onChanged={reloadActionItems}
          />

          <SectionTitle>最近进展</SectionTitle>
          {recentProgress.length === 0 ? (
            <EmptyState title="暂无进展" />
          ) : (
            <>
              <DataToolbar
                keyword={progressList.keyword}
                onKeywordChange={progressList.setKeyword}
                searchPlaceholder="搜索任务 / 内容 / 提交人"
                onReset={progressList.reset}
                summary={`共 ${progressList.total} 条`}
              />
              {progressList.paged.length === 0 ? (
                <EmptyState title="无匹配结果" description="试试调整关键词。" />
              ) : (
                <div className="card-grid">
                  {progressList.paged.map((item) => (
                    <AppCard key={item.id} as="article" stack="sm">
                      <div className="meta-line">
                        {item.task_name} · {item.user_name} ·{" "}
                        {new Date(item.created_at).toLocaleString("zh-CN")}
                      </div>
                      <p className="detail-text">{item.raw_content}</p>
                      {item.summary ? (
                        <p className="meta-line meta-line--accent">AI 摘要 · {item.summary}</p>
                      ) : null}
                    </AppCard>
                  ))}
                </div>
              )}
              <AppPagination
                page={progressList.page}
                pageSize={progressList.pageSize}
                total={progressList.total}
                onPageChange={progressList.setPage}
                onPageSizeChange={progressList.setPageSize}
              />
            </>
          )}
        </div>

        <aside className="project-detail-layout__aside">
          <ProjectIssuesPanel
            projectId={projectId}
            issues={openIssues}
            canCreate={canContribute}
            taskOptions={taskOptions}
            onChanged={reloadOpenIssues}
          />

          <div>
            <SectionTitle
              flush
              extra={
                canManage ? (
                  <Button
                    size="small"
                    loading={regenLoading}
                    onClick={() => void onRegenerateSummary()}
                  >
                    重新生成
                  </Button>
                ) : null
              }
            >
              每日摘要
            </SectionTitle>
            {summaryStatus === "QUEUED" || summaryStatus === "RUNNING" ? (
              <AppCard>
                <p className="meta-line meta-line--accent">摘要生成中…</p>
              </AppCard>
            ) : null}
            {summaryStatus === "FAILED" ? (
              <AppCard>
                <p className="meta-line" style={{ color: "var(--app-color-danger)" }}>
                  ⚠ 摘要生成失败
                </p>
              </AppCard>
            ) : null}
            {summaryStatus === "DISABLED" ? (
              <AppCard>
                <p className="meta-line">LLM 未启用</p>
              </AppCard>
            ) : null}
            {!latestSummary ? (
              <AppCard>
                <p className="meta-line">暂无每日摘要</p>
              </AppCard>
            ) : (
              <AppCard as="article" stack="md">
                <div className="meta-line">{latestSummary.summary_date}</div>
                <p className="detail-text">{latestSummary.summary}</p>
                <div>
                  <span className="field-label">风险</span>
                  <p className="detail-text">{latestSummary.risk_summary}</p>
                </div>
                <div>
                  <span className="field-label">下一关键节点</span>
                  <p className="detail-text">{latestSummary.next_action}</p>
                </div>
                <div>
                  <span className="field-label">需要管理层介入</span>
                  <p className="detail-text">{latestSummary.management_attention}</p>
                </div>
              </AppCard>
            )}
          </div>
        </aside>
      </div>
    </PageContainer>
  );
}

export default function ProjectDetailPage() {
  return (
    <RequireAuth>
      <ProjectDetailInner />
    </RequireAuth>
  );
}

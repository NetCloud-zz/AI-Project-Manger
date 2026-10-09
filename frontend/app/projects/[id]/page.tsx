"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { App, AutoComplete, Button, DatePicker, Form, Input, Select, Segmented } from "antd";
import { BarChartOutlined, PlusOutlined, UnorderedListOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { ActionGroup } from "@/components/common/ActionGroup";
import { AppCard } from "@/components/common/AppCard";
import { SectionTitle } from "@/components/common/SectionTitle";
import { AppPagination } from "@/components/data/AppPagination";
import { DataToolbar } from "@/components/data/DataToolbar";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ExplanationDisclosure } from "@/components/feedback/ExplanationDisclosure";
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
import { canManageProject } from "@/lib/permissions";
import { fetchProjectActionItems } from "@/services/action_items";
import {
  createProjectTask,
  fetchAssignableUsers,
  fetchProject,
  fetchProjectTasks,
} from "@/services/projects";
import { fetchProjectRecentProgress } from "@/services/progress";
import { fetchProjectOpenIssues } from "@/services/issues";
import { fetchLatestProjectSummary, regenerateProjectSummary } from "@/services/summaries";
import { fetchAIRun } from "@/services/ai_runs";
import type { ActionItem } from "@/types/action_item";
import type { Project, ProjectOwnerBrief } from "@/types/project";
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
  const [tasksError, setTasksError] = useState("");
  const [tasksLoading, setTasksLoading] = useState(true);
  const [recentProgress, setRecentProgress] = useState<RecentProgressItem[]>([]);
  const [progressError, setProgressError] = useState("");
  const [progressLoading, setProgressLoading] = useState(true);
  const [openIssues, setOpenIssues] = useState<Issue[]>([]);
  const [issuesError, setIssuesError] = useState("");
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [actionItemsError, setActionItemsError] = useState("");
  const [latestSummary, setLatestSummary] = useState<DailyProjectSummary | null>(null);
  const [summaryError, setSummaryError] = useState("");
  const [summaryStatus, setSummaryStatus] = useState<string | null>(null);
  const [summaryTimedOut, setSummaryTimedOut] = useState(false);
  const [assignableUsers, setAssignableUsers] = useState<ProjectOwnerBrief[]>([]);
  const [regenLoading, setRegenLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [taskView, setTaskView] = useState<"list" | "gantt">("list");
  const [taskForm] = Form.useForm<{
    task_name: string;
    work_stream?: string;
    owner_id?: number | null;
    date_range?: [dayjs.Dayjs, dayjs.Dayjs] | null;
  }>();

  const reloadTasks = useCallback(async () => {
    setTasksLoading(true);
    setTasksError("");
    try {
      setTasks(await fetchProjectTasks(projectId));
    } catch (err) {
      setTasksError(err instanceof Error ? err.message : "任务加载失败");
    } finally {
      setTasksLoading(false);
    }
  }, [projectId]);

  const reloadActionItems = useCallback(async () => {
    setActionItemsError("");
    try {
      setActionItems(await fetchProjectActionItems(projectId));
    } catch (err) {
      setActionItemsError(err instanceof Error ? err.message : "待办加载失败");
    }
  }, [projectId]);

  const reloadOpenIssues = useCallback(async () => {
    setIssuesError("");
    try {
      setOpenIssues(await fetchProjectOpenIssues(projectId));
    } catch (err) {
      setIssuesError(err instanceof Error ? err.message : "问题加载失败");
    }
  }, [projectId]);

  const reloadProgress = useCallback(async () => {
    setProgressLoading(true);
    setProgressError("");
    try {
      setRecentProgress(await fetchProjectRecentProgress(projectId));
    } catch (err) {
      setProgressError(err instanceof Error ? err.message : "进展加载失败");
    } finally {
      setProgressLoading(false);
    }
  }, [projectId]);

  const reloadSummary = useCallback(async () => {
    setSummaryError("");
    try {
      setLatestSummary(await fetchLatestProjectSummary(projectId));
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : "摘要加载失败");
    }
  }, [projectId]);

  const loadCore = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const [p, users] = await Promise.all([
        fetchProject(projectId),
        fetchAssignableUsers(projectId).catch(() => [] as ProjectOwnerBrief[]),
      ]);
      setProject(p);
      setAssignableUsers(users);
    } catch {
      setFailed(true);
      setProject(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (cancelled) return;
      void loadCore();
      void reloadTasks();
      void reloadProgress();
      void reloadOpenIssues();
      void reloadActionItems();
      void reloadSummary();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [loadCore, reloadActionItems, reloadOpenIssues, reloadProgress, reloadSummary, reloadTasks]);

  const canManage = canManageProject(user, project);

  const activeTasks = tasks.filter((task) => task.is_active_branch !== false);
  const taskList = usePagedList({
    items: activeTasks,
    searchFields: (item) => [
      item.task_name,
      item.work_stream,
      item.branch_label,
      item.owner?.name,
      ...(item.owners ?? []).map((owner) => owner.name),
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
    setSummaryTimedOut(false);
    setSummaryStatus("QUEUED");
    try {
      const res = await regenerateProjectSummary(projectId);
      message.success("每日摘要生成中…");
      const started = Date.now();
      let finished = false;
      while (Date.now() - started < 120_000) {
        await new Promise((r) => setTimeout(r, 2500));
        const run = await fetchAIRun(res.ai_run_id);
        setSummaryStatus(run.status);
        if (
          run.status === "SUCCEEDED" ||
          run.status === "FAILED" ||
          run.status === "DISABLED"
        ) {
          finished = true;
          if (run.status === "SUCCEEDED") {
            await reloadSummary();
            message.success("每日摘要已更新");
          } else if (run.status === "DISABLED") {
            message.warning(run.user_message || "LLM 未启用");
          } else {
            message.error(run.user_message || "摘要生成失败");
          }
          break;
        }
      }
      if (!finished) {
        setSummaryTimedOut(true);
        setSummaryStatus(null);
        message.info("摘要仍在生成，可稍后刷新或再次查询状态");
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
      taskForm.resetFields();
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
        <ErrorState description="无法获取项目详情，请稍后重试。" onRetry={() => void loadCore()} />
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
        ...assignableUsers.map((u) => ({ id: u.id, name: u.name })),
      ]
        .filter((entry): entry is { id: number; name: string } => entry != null)
        .map((entry) => [entry.id, { value: entry.id, label: entry.name }] as const),
    ).values(),
  );
  const assignableOptions =
    assignableUsers.length > 0
      ? assignableUsers.map((u) => ({
          value: u.id,
          label: `${u.name}（${u.username}）`,
        }))
      : ownerOptions;

  return (
    <PageContainer>
      <PageHeader
        backHref="/projects"
        backLabel="项目列表"
        title={project.project_name}
        meta={
          <span>
            {project.project_code}
            {project.goal ? ` · ${project.goal}` : ""}
          </span>
        }
        subtitle={
          <div className="chip-row chip-row--flush">
            <ProjectStatusTag status={project.status} />
            <RiskTag level={project.risk_level} />
          </div>
        }
        action={
          <ActionGroup>
            <Button href={`/projects/${projectId}/planning`}>计划资料与路线</Button>
            <Button href={`/projects/${projectId}/risks`}>风险与建议</Button>
            {canManage ? (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setShowTaskForm((value) => !value)}
              >
                {showTaskForm ? "取消" : "新建任务"}
              </Button>
            ) : null}
          </ActionGroup>
        }
      />

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
          <Form form={taskForm} layout="vertical" onFinish={onCreateTask}>
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
              label="负责人"
              name="owner_id"
              extra="可选；可先创建任务，负责人后续再指派。"
            >
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder="选择负责人（可留空）"
                options={assignableOptions}
                notFoundContent="暂无可选人员"
              />
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

          {tasksError ? (
            <ErrorState description={tasksError} onRetry={() => void reloadTasks()} />
          ) : tasksLoading ? (
            <LoadingState tip="加载任务…" />
          ) : taskView === "gantt" ? (
            <ProjectGanttPanel projectId={projectId} />
          ) : activeTasks.length === 0 ? (
            <EmptyState
              compact
              title="暂无任务"
              description="创建任务以开始跟踪进度。"
              action={
                canManage ? (
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowTaskForm(true)}>
                    新建任务
                  </Button>
                ) : undefined
              }
            />
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
                <EmptyState compact title="无匹配结果" description="试试调整关键词。" />
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

          {actionItemsError ? (
            <ErrorState description={actionItemsError} onRetry={() => void reloadActionItems()} />
          ) : (
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
          )}

          <SectionTitle>最近进展</SectionTitle>
          {progressError ? (
            <ErrorState description={progressError} onRetry={() => void reloadProgress()} />
          ) : progressLoading ? (
            <LoadingState tip="加载进展…" />
          ) : recentProgress.length === 0 ? (
            <EmptyState compact title="暂无进展" />
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
                <EmptyState compact title="无匹配结果" description="试试调整关键词。" />
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
          {issuesError ? (
            <ErrorState description={issuesError} onRetry={() => void reloadOpenIssues()} />
          ) : (
            <ProjectIssuesPanel
              projectId={projectId}
              issues={openIssues}
              canCreate={canContribute}
              taskOptions={taskOptions}
              onChanged={reloadOpenIssues}
            />
          )}

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
            {summaryError ? (
              <ErrorState description={summaryError} onRetry={() => void reloadSummary()} />
            ) : null}
            {summaryStatus === "QUEUED" || summaryStatus === "RUNNING" ? (
              <AppCard>
                <p className="meta-line meta-line--accent">摘要生成中…</p>
              </AppCard>
            ) : null}
            {summaryTimedOut ? (
              <AppCard>
                <p className="meta-line">摘要仍在生成，可稍后刷新或点击重新生成查询状态。</p>
              </AppCard>
            ) : null}
            {summaryStatus === "FAILED" ? (
              <AppCard>
                <p className="meta-line" style={{ color: "var(--app-color-danger)" }}>
                  摘要生成失败
                </p>
              </AppCard>
            ) : null}
            {summaryStatus === "DISABLED" ? (
              <AppCard>
                <p className="meta-line">LLM 未启用</p>
              </AppCard>
            ) : null}
            {!latestSummary && !summaryError ? (
              <EmptyState compact title="暂无每日摘要" />
            ) : latestSummary ? (
              <AppCard as="article" stack="md">
                <div className="meta-line">{latestSummary.summary_date}</div>
                <p className="detail-text">{latestSummary.summary}</p>
                <ExplanationDisclosure
                  summary={
                    <div className="stack-sm">
                      <div>
                        <span className="field-label">关键风险</span>
                        <p className="detail-text">{latestSummary.risk_summary}</p>
                      </div>
                      <div>
                        <span className="field-label">下一关键节点</span>
                        <p className="detail-text">{latestSummary.next_action}</p>
                      </div>
                    </div>
                  }
                  expandCount={1}
                >
                  <div>
                    <span className="field-label">需要管理层介入</span>
                    <p className="detail-text">{latestSummary.management_attention}</p>
                  </div>
                </ExplanationDisclosure>
              </AppCard>
            ) : null}
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

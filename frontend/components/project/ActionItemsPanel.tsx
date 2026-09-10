"use client";

import { useMemo, useState } from "react";
import { App, Button, DatePicker, Form, Input, Modal, Segmented, Select } from "antd";
import { CheckOutlined, PlusOutlined, UndoOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { AppCard } from "@/components/common/AppCard";
import { SectionTitle } from "@/components/common/SectionTitle";
import { AppPagination } from "@/components/data/AppPagination";
import { DataToolbar } from "@/components/data/DataToolbar";
import { EmptyState } from "@/components/feedback/EmptyState";
import {
  ACTION_ITEM_PRIORITY_OPTIONS,
  ActionItemPriorityTag,
  ActionItemStatusTag,
} from "@/components/project/StatusTags";
import { usePagedList } from "@/hooks/usePagedList";
import { createProjectActionItem, updateActionItem } from "@/services/action_items";
import type { ActionItem, ActionItemPriority } from "@/types/action_item";
import { isActionItemOpen } from "@/types/action_item";

type Option = { value: number; label: string };

type Props = {
  projectId: number;
  items: ActionItem[];
  /** Project owners and admins may manage every item. */
  canManageAll: boolean;
  canCreate: boolean;
  currentUserId?: number;
  ownerOptions: Option[];
  taskOptions: Option[];
  issueOptions: Option[];
  onChanged: () => void | Promise<void>;
};

type FormValues = {
  title: string;
  description?: string;
  owner_id?: number;
  priority?: ActionItemPriority;
  due_date?: dayjs.Dayjs;
  task_id?: number;
  issue_id?: number;
};

export function ActionItemsPanel({
  projectId,
  items,
  canManageAll,
  canCreate,
  currentUserId,
  ownerOptions,
  taskOptions,
  issueOptions,
  onChanged,
}: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm<FormValues>();
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [scope, setScope] = useState<"open" | "all">("open");

  const visible = useMemo(
    () => (scope === "open" ? items.filter(isActionItemOpen) : items),
    [items, scope],
  );
  const openCount = useMemo(() => items.filter(isActionItemOpen).length, [items]);
  const list = usePagedList({
    items: visible,
    searchFields: (item) => [
      item.title,
      item.description,
      item.owner?.name,
      item.task?.task_name,
      item.issue?.title,
    ],
    defaultPageSize: 10,
  });

  const canModify = (item: ActionItem) =>
    canManageAll || item.owner_id === currentUserId || item.created_by === currentUserId;

  const submit = async (values: FormValues) => {
    setSubmitting(true);
    try {
      await createProjectActionItem(projectId, {
        title: values.title,
        description: values.description ?? null,
        owner_id: values.owner_id ?? null,
        task_id: values.task_id ?? null,
        issue_id: values.issue_id ?? null,
        due_date: values.due_date ? values.due_date.format("YYYY-MM-DD") : null,
        priority: values.priority ?? "MEDIUM",
      });
      message.success("行动项已创建");
      setFormOpen(false);
      form.resetFields();
      await onChanged();
    } catch {
      message.error("创建行动项失败");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleDone = async (item: ActionItem) => {
    setBusyId(item.id);
    const nextStatus = isActionItemOpen(item) ? "DONE" : "OPEN";
    try {
      await updateActionItem(item.id, { status: nextStatus });
      await onChanged();
    } catch {
      message.error("更新行动项失败");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <SectionTitle
        extra={
          <div className="chip-row chip-row--flush">
            <Segmented
              size="small"
              value={scope}
              onChange={(value) => setScope(value as "open" | "all")}
              options={[
                { value: "open", label: `未完成 ${openCount}` },
                { value: "all", label: `全部 ${items.length}` },
              ]}
            />
            {canCreate ? (
              <Button size="small" icon={<PlusOutlined />} onClick={() => setFormOpen(true)}>
                新建
              </Button>
            ) : null}
          </div>
        }
      >
        行动项
      </SectionTitle>

      {visible.length === 0 ? (
        <EmptyState
          title={scope === "open" ? "暂无未完成行动项" : "暂无行动项"}
          description="行动项用于跟踪「谁在什么时间之前要做什么」。"
        />
      ) : (
        <>
          <DataToolbar
            keyword={list.keyword}
            onKeywordChange={list.setKeyword}
            searchPlaceholder="搜索行动项 / 负责人 / 任务"
            onReset={list.reset}
            summary={`共 ${list.total} 条`}
          />
          {list.paged.length === 0 ? (
            <EmptyState title="无匹配结果" description="试试调整关键词。" />
          ) : (
            <div className="card-grid">
              {list.paged.map((item) => {
                const overdue =
                  item.due_date && isActionItemOpen(item)
                    ? dayjs(item.due_date).isBefore(dayjs(), "day")
                    : false;
                const meta = [
                  `负责人：${item.owner?.name ?? "未指派"}`,
                  item.due_date ? `截止：${item.due_date}${overdue ? "（已逾期）" : ""}` : null,
                  item.task ? `任务：${item.task.task_name}` : null,
                  item.issue ? `问题：${item.issue.title}` : null,
                ].filter(Boolean);

                return (
                  <AppCard key={item.id} as="article" stack="sm">
                    <div className="entity-card__head">
                      <span className="entity-card__name">{item.title}</span>
                      {canModify(item) ? (
                        <Button
                          size="small"
                          type="text"
                          loading={busyId === item.id}
                          icon={isActionItemOpen(item) ? <CheckOutlined /> : <UndoOutlined />}
                          onClick={() => toggleDone(item)}
                        >
                          {isActionItemOpen(item) ? "完成" : "重开"}
                        </Button>
                      ) : null}
                    </div>
                    <div className="chip-row chip-row--flush">
                      <ActionItemStatusTag status={item.status} />
                      <ActionItemPriorityTag priority={item.priority} />
                    </div>
                    {item.description ? <p className="detail-text">{item.description}</p> : null}
                    <p className={`meta-line${overdue ? " meta-line--danger" : ""}`}>
                      {meta.join(" · ")}
                    </p>
                  </AppCard>
                );
              })}
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

      <Modal
        title="新建行动项"
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={() => form.submit()}
        okText="保存"
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item label="内容" name="title" rules={[{ required: true, max: 300 }]}>
            <Input placeholder="例如：向 CRO 索要原始数据" />
          </Form.Item>
          <Form.Item label="说明" name="description">
            <Input.TextArea rows={3} placeholder="补充背景或验收标准（可选）" />
          </Form.Item>
          <Form.Item label="负责人" name="owner_id">
            <Select allowClear placeholder="未指派" options={ownerOptions} />
          </Form.Item>
          <Form.Item label="优先级" name="priority" initialValue="MEDIUM">
            <Select options={ACTION_ITEM_PRIORITY_OPTIONS} />
          </Form.Item>
          <Form.Item label="截止日期" name="due_date">
            <DatePicker className="full-width" />
          </Form.Item>
          <Form.Item label="关联任务" name="task_id">
            <Select allowClear placeholder="可选" options={taskOptions} />
          </Form.Item>
          <Form.Item label="关联问题" name="issue_id">
            <Select allowClear placeholder="可选" options={issueOptions} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import { App, Button, Form, Input, Modal, Select } from "antd";
import { PlusOutlined } from "@ant-design/icons";

import { AppCard } from "@/components/common/AppCard";
import { SectionTitle } from "@/components/common/SectionTitle";
import { AppPagination } from "@/components/data/AppPagination";
import { DataToolbar } from "@/components/data/DataToolbar";
import { EmptyState } from "@/components/feedback/EmptyState";
import {
  ISSUE_SEVERITY_OPTIONS,
  IssueSeverityTag,
  IssueStatusTag,
} from "@/components/project/StatusTags";
import { usePagedList } from "@/hooks/usePagedList";
import { createProjectIssue } from "@/services/issues";
import type { Issue, IssueSeverity } from "@/types/issue";

type Option = { value: number; label: string };

type Props = {
  projectId: number;
  issues: Issue[];
  canCreate: boolean;
  taskOptions: Option[];
  onChanged: () => void | Promise<void>;
};

type FormValues = {
  title: string;
  description: string;
  severity?: IssueSeverity;
  task_id?: number;
};

export function ProjectIssuesPanel({
  projectId,
  issues,
  canCreate,
  taskOptions,
  onChanged,
}: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm<FormValues>();
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const list = usePagedList({
    items: issues,
    searchFields: (item) => [item.title, item.description, item.task?.task_name],
    defaultPageSize: 10,
  });

  const submit = async (values: FormValues) => {
    setSubmitting(true);
    try {
      await createProjectIssue(projectId, {
        title: values.title,
        description: values.description,
        severity: values.severity ?? "MEDIUM",
        task_id: values.task_id ?? null,
      });
      message.success("问题已登记");
      setFormOpen(false);
      form.resetFields();
      await onChanged();
    } catch {
      message.error("登记问题失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <SectionTitle
        flush
        extra={
          canCreate ? (
            <Button size="small" icon={<PlusOutlined />} onClick={() => setFormOpen(true)}>
              登记
            </Button>
          ) : undefined
        }
      >
        待解决的问题
      </SectionTitle>

      {issues.length === 0 ? (
        <AppCard>
          <p className="meta-line">暂无待解决的问题</p>
        </AppCard>
      ) : (
        <>
          <DataToolbar
            keyword={list.keyword}
            onKeywordChange={list.setKeyword}
            searchPlaceholder="搜索问题 / 任务"
            onReset={list.reset}
            summary={`共 ${list.total} 条`}
          />
          {list.paged.length === 0 ? (
            <EmptyState title="无匹配结果" description="试试调整关键词。" />
          ) : (
            <div className="card-grid">
              {list.paged.map((item) => (
                <Link
                  key={item.id}
                  href={`/issues/${item.id}`}
                  className="app-card app-card--interactive list-link"
                >
                  <div className="entity-card__name">{item.title}</div>
                  <div className="chip-row">
                    <IssueSeverityTag severity={item.severity} />
                    <IssueStatusTag status={item.status} />
                  </div>
                  <p className="meta-line">
                    {item.task ? `任务：${item.task.task_name}` : "项目级问题"}
                  </p>
                </Link>
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

      <Modal
        title="登记待解决的问题"
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={() => form.submit()}
        okText="保存"
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item label="标题" name="title" rules={[{ required: true, max: 300 }]}>
            <Input placeholder="例如：伦理委员会反馈未到" />
          </Form.Item>
          <Form.Item label="描述" name="description" rules={[{ required: true }]}>
            <Input.TextArea rows={4} placeholder="问题现状、影响范围、已尝试的措施" />
          </Form.Item>
          <Form.Item label="严重程度" name="severity" initialValue="MEDIUM">
            <Select options={ISSUE_SEVERITY_OPTIONS} />
          </Form.Item>
          <Form.Item
            label="关联任务"
            name="task_id"
            extra="留空表示这是项目级问题，不绑定具体任务。"
          >
            <Select allowClear placeholder="可选" options={taskOptions} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

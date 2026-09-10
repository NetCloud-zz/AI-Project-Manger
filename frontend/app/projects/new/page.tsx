"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { App, Button, DatePicker, Form, Input } from "antd";
import dayjs from "dayjs";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppCard } from "@/components/common/AppCard";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import { ApiError } from "@/lib/http";
import { createProject } from "@/services/projects";

function NewProjectPageInner() {
  const router = useRouter();
  const { message } = App.useApp();
  const { user } = useAuth();
  const [submitting, setSubmitting] = useState(false);

  const onFinish = async (values: {
    project_code: string;
    project_name: string;
    goal?: string;
    target_date?: dayjs.Dayjs;
  }) => {
    if (!user) return;
    setSubmitting(true);
    try {
      const project = await createProject({
        project_code: values.project_code,
        project_name: values.project_name,
        goal: values.goal,
        owner_id: user.id,
        target_date: values.target_date ? values.target_date.format("YYYY-MM-DD") : null,
      });
      message.success("项目已创建");
      router.push(`/projects/${project.id}`);
    } catch (error) {
      const detail =
        error instanceof ApiError &&
        typeof error.payload === "object" &&
        error.payload &&
        "detail" in error.payload
          ? String((error.payload as { detail: unknown }).detail)
          : "创建失败";
      message.error(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PageContainer width="form">
      <PageHeader
        backHref="/projects"
        backLabel="项目列表"
        title="新建项目"
        subtitle="创建后可添加任务并跟踪进展。"
      />

      <AppCard>
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item label="项目编号" name="project_code" rules={[{ required: true }]}>
            <Input placeholder="PRJ-1001" />
          </Form.Item>
          <Form.Item label="项目名称" name="project_name" rules={[{ required: true }]}>
            <Input placeholder="输入项目名称" />
          </Form.Item>
          <Form.Item label="项目目标" name="goal">
            <Input.TextArea rows={3} placeholder="可选，描述项目目标" />
          </Form.Item>
          <Form.Item label="目标日期" name="target_date">
            <DatePicker className="full-width" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={submitting}>
            创建项目
          </Button>
        </Form>
      </AppCard>
    </PageContainer>
  );
}

export default function NewProjectPage() {
  return (
    <RequireAuth>
      <NewProjectPageInner />
    </RequireAuth>
  );
}

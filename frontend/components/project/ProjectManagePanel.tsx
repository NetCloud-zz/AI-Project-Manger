"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { App, Button, DatePicker, Form, Input, Modal, Select } from "antd";
import { CalendarOutlined, DeleteOutlined, TeamOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { AppCard } from "@/components/common/AppCard";
import { ScheduleImpactModal } from "@/components/project/ScheduleImpactModal";
import { ApiError } from "@/lib/http";
import { scheduleImpactOf, type ScheduleImpact } from "@/lib/schedule-impact";
import {
  deleteProject,
  fetchAssignableUsers,
  updateProjectOwners,
  updateProjectSchedule,
} from "@/services/projects";
import type { Project, ProjectOwnerBrief } from "@/types/project";

type Props = {
  project: Project;
  canManage: boolean;
  onChanged: (project: Project) => void;
};

function errorDetail(error: unknown): string | undefined {
  if (
    error instanceof ApiError &&
    error.payload &&
    typeof error.payload === "object" &&
    "detail" in error.payload &&
    typeof (error.payload as { detail: unknown }).detail === "string"
  ) {
    return (error.payload as { detail: string }).detail;
  }
  return undefined;
}

export function ProjectManagePanel({ project, canManage, onChanged }: Props) {
  const { message } = App.useApp();
  const router = useRouter();
  const [ownersOpen, setOwnersOpen] = useState(false);
  const [impact, setImpact] = useState<ScheduleImpact | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [candidates, setCandidates] = useState<ProjectOwnerBrief[]>([]);
  const [saving, setSaving] = useState(false);
  const [ownersForm] = Form.useForm<{ owner_ids: number[] }>();
  const [scheduleForm] = Form.useForm<{
    range?: [dayjs.Dayjs | null, dayjs.Dayjs | null];
    change_reason: string;
  }>();
  const [deleteForm] = Form.useForm<{ reason: string }>();

  useEffect(() => {
    if (!canManage || (!ownersOpen && !scheduleOpen)) return;
    let cancelled = false;
    fetchAssignableUsers(project.id)
      .then((users) => {
        if (!cancelled) setCandidates(users);
      })
      .catch(() => {
        if (!cancelled) message.error("加载可选用户失败");
      });
    return () => {
      cancelled = true;
    };
  }, [canManage, message, ownersOpen, project.id, scheduleOpen]);

  const ownerNames =
    (project.owners?.length ? project.owners : project.owner ? [project.owner] : [])
      .map((o) => o.name)
      .join("、") || "未设置";

  const scheduleLabel = [
    project.start_date ? `开始 ${project.start_date}` : null,
    project.target_date ? `目标 ${project.target_date}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const openOwners = () => {
    const ids =
      project.owners?.map((o) => o.id) ??
      (project.owner_id ? [project.owner_id] : []);
    ownersForm.setFieldsValue({ owner_ids: ids });
    setOwnersOpen(true);
  };

  const openSchedule = () => {
    scheduleForm.setFieldsValue({
      range: [
        project.start_date ? dayjs(project.start_date) : null,
        project.target_date ? dayjs(project.target_date) : null,
      ],
      change_reason: "",
    });
    setScheduleOpen(true);
  };

  const openDelete = () => {
    deleteForm.setFieldsValue({ reason: "" });
    setDeleteOpen(true);
  };

  const saveOwners = async (values: { owner_ids: number[] }) => {
    setSaving(true);
    try {
      const updated = await updateProjectOwners(project.id, {
        owner_ids: values.owner_ids,
      });
      onChanged(updated);
      setOwnersOpen(false);
      message.success("负责人已更新");
    } catch {
      message.error("更新负责人失败");
    } finally {
      setSaving(false);
    }
  };

  const saveSchedule = async (values: {
    range?: [dayjs.Dayjs | null, dayjs.Dayjs | null];
    change_reason: string;
  }) => {
    const [start, target] = values.range ?? [null, null];
    const body: {
      start_date?: string | null;
      target_date?: string | null;
      change_reason: string;
    } = { change_reason: values.change_reason.trim() };
    const nextStart = start ? start.format("YYYY-MM-DD") : null;
    const nextTarget = target ? target.format("YYYY-MM-DD") : null;
    if (nextStart !== project.start_date) body.start_date = nextStart;
    if (nextTarget !== project.target_date) body.target_date = nextTarget;

    setSaving(true);
    try {
      const updated = await updateProjectSchedule(project.id, body);
      onChanged(updated);
      setScheduleOpen(false);
      message.success("项目时间已更新");
    } catch (error: unknown) {
      const ripple = scheduleImpactOf(error);
      if (ripple) {
        setScheduleOpen(false);
        setImpact(ripple);
        return;
      }
      message.error(errorDetail(error) ?? "更新项目时间失败");
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async (values: { reason: string }) => {
    setSaving(true);
    try {
      await deleteProject(project.id, { reason: values.reason.trim() });
      message.success("项目已删除");
      setDeleteOpen(false);
      router.push("/projects");
    } catch (error) {
      message.error(errorDetail(error) ?? "删除项目失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <AppCard stack="sm">
        <div className="meta-line">
          <TeamOutlined /> 负责人：{ownerNames}
          {canManage ? (
            <Button type="link" size="small" onClick={openOwners}>
              编辑
            </Button>
          ) : null}
        </div>
        <div className="meta-line">
          <CalendarOutlined /> 整体时间：{scheduleLabel || "未设置"}
          {canManage ? (
            <Button type="link" size="small" onClick={openSchedule}>
              调整
            </Button>
          ) : null}
        </div>
        {canManage ? (
          <div className="meta-line">
            <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={openDelete}>
              删除项目
            </Button>
          </div>
        ) : null}
      </AppCard>

      <Modal
        title="设置项目负责人"
        open={ownersOpen}
        onCancel={() => setOwnersOpen(false)}
        onOk={() => ownersForm.submit()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={ownersForm} layout="vertical" onFinish={saveOwners}>
          <Form.Item
            label="负责人（可多选）"
            name="owner_ids"
            rules={[{ required: true, message: "至少选择一位负责人" }]}
            extra="可多选；所选人员均为项目负责人，权限相同，均可管理项目与调整整体时间。"
          >
            <Select
              mode="multiple"
              optionFilterProp="label"
              placeholder="选择负责人"
              options={candidates.map((u) => ({
                value: u.id,
                label: `${u.name}（${u.username}）`,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="调整项目整体时间"
        open={scheduleOpen}
        onCancel={() => setScheduleOpen(false)}
        onOk={() => scheduleForm.submit()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={scheduleForm} layout="vertical" onFinish={saveSchedule}>
          <Form.Item label="起止日期" name="range">
            <DatePicker.RangePicker
              className="full-width"
              allowEmpty={[true, true]}
              placeholder={["开始日期", "目标日期"]}
            />
          </Form.Item>
          <Form.Item
            label="变更说明"
            name="change_reason"
            rules={[{ required: true, min: 2, message: "请填写变更原因" }]}
            extra="必填。说明会写入审计日志，便于追溯。"
          >
            <Input.TextArea
              rows={3}
              maxLength={2000}
              showCount
              placeholder="例如：目标日与业务承诺对齐"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="删除项目"
        open={deleteOpen}
        onCancel={() => setDeleteOpen(false)}
        onOk={() => deleteForm.submit()}
        okText="确认删除"
        okButtonProps={{ danger: true }}
        confirmLoading={saving}
        destroyOnHidden
      >
        <p className="detail-text">
          将永久删除项目「{project.project_code}」及其任务、问题、风险等关联数据，且不可恢复。
          仅项目负责人或管理员可操作，删除原因会写入审计日志。
        </p>
        <Form form={deleteForm} layout="vertical" onFinish={confirmDelete}>
          <Form.Item
            label="删除原因"
            name="reason"
            rules={[{ required: true, min: 2, message: "请填写删除原因" }]}
          >
            <Input.TextArea rows={3} maxLength={2000} showCount placeholder="请说明删除原因" />
          </Form.Item>
        </Form>
      </Modal>

      <ScheduleImpactModal
        projectId={project.id}
        impact={impact}
        onClose={() => setImpact(null)}
      />
    </>
  );
}

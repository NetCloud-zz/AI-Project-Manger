"use client";

import { useCallback, useEffect, useState } from "react";
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  KeyOutlined,
  PlusOutlined,
  StopOutlined,
  CheckCircleOutlined,
  EditOutlined,
  CloudSyncOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppPagination } from "@/components/data/AppPagination";
import { DataToolbar } from "@/components/data/DataToolbar";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import { usePagedList } from "@/hooks/usePagedList";
import { useViewport } from "@/hooks/useViewport";
import { ApiError } from "@/lib/http";
import {
  ROLE_LABELS,
  ROLE_OPTIONS,
  STATUS_LABELS,
  STATUS_OPTIONS,
} from "@/lib/navigation";
import {
  createUser,
  deactivateUser,
  fetchUsers,
  resetUserPassword,
  syncUsersFromOa,
  updateUser,
  type ManagedUser,
  type UserCreateInput,
  type UserRole,
  type UserUpdateInput,
} from "@/services/users";

type EditorMode = "create" | "edit";

const FILTERS = [
  { key: "role", placeholder: "角色", options: ROLE_OPTIONS },
  { key: "status", placeholder: "状态", options: STATUS_OPTIONS },
];

const SEARCH_FIELDS = (item: ManagedUser) => [
  item.name,
  item.username,
  item.email,
  item.department,
  item.mobile,
];

const MATCHERS = {
  role: (item: ManagedUser, value: string) => item.role === value,
  status: (item: ManagedUser, value: string) => item.status === value,
};

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const payload = error.payload as { detail?: string } | null;
    if (payload?.detail && typeof payload.detail === "string") return payload.detail;
  }
  return fallback;
}

function UsersPageInner() {
  const { message, modal } = App.useApp();
  const { user: me } = useAuth();
  const viewport = useViewport();
  const isCompact = viewport === "mobile" || viewport === "tablet";
  const isAdmin = me?.role === "ADMIN";
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(isAdmin);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState<EditorMode>("create");
  const [editing, setEditing] = useState<ManagedUser | null>(null);
  const [saving, setSaving] = useState(false);
  const [editorForm] = Form.useForm<UserCreateInput & UserUpdateInput>();

  const [passwordOpen, setPasswordOpen] = useState(false);
  const [passwordTarget, setPasswordTarget] = useState<ManagedUser | null>(null);
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordForm] = Form.useForm<{ password: string; confirm: string }>();
  const [syncingOa, setSyncingOa] = useState(false);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    fetchUsers()
      .then((data) => {
        if (!cancelled) {
          setUsers(data);
          setFailed(false);
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
  }, [reloadKey, isAdmin]);

  const retry = useCallback(() => {
    setLoading(true);
    setFailed(false);
    setReloadKey((value) => value + 1);
  }, []);

  const list = usePagedList({
    items: users,
    searchFields: SEARCH_FIELDS,
    filterMatchers: MATCHERS,
    defaultPageSize: 20,
  });

  const openCreate = () => {
    setEditorMode("create");
    setEditing(null);
    editorForm.resetFields();
    editorForm.setFieldsValue({ role: "MEMBER" });
    setEditorOpen(true);
  };

  const openEdit = (record: ManagedUser) => {
    setEditorMode("edit");
    setEditing(record);
    editorForm.setFieldsValue({
      name: record.name,
      email: record.email ?? undefined,
      mobile: record.mobile ?? undefined,
      department: record.department ?? undefined,
      wechat_user_id: record.wechat_user_id ?? undefined,
      role: record.role,
      status: record.status,
    });
    setEditorOpen(true);
  };

  const openPassword = (record: ManagedUser) => {
    setPasswordTarget(record);
    passwordForm.resetFields();
    setPasswordOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await editorForm.validateFields();
      setSaving(true);
      if (editorMode === "create") {
        await createUser({
          name: values.name!,
          username: values.username!,
          password: values.password!,
          email: values.email || null,
          mobile: values.mobile || null,
          department: values.department || null,
          wechat_user_id: values.wechat_user_id || null,
          role: (values.role as UserRole) || "MEMBER",
        });
        message.success("用户已创建");
      } else if (editing) {
        await updateUser(editing.id, {
          name: values.name,
          email: values.email || null,
          mobile: values.mobile || null,
          department: values.department || null,
          wechat_user_id: values.wechat_user_id || null,
          role: values.role as UserRole | undefined,
          status: values.status as ManagedUser["status"] | undefined,
        });
        message.success("用户已更新");
      }
      setEditorOpen(false);
      retry();
    } catch (error) {
      if (error && typeof error === "object" && "errorFields" in error) return;
      message.error(errorMessage(error, "保存失败"));
    } finally {
      setSaving(false);
    }
  };

  const handlePasswordSave = async () => {
    if (!passwordTarget) return;
    try {
      const values = await passwordForm.validateFields();
      setPasswordSaving(true);
      await resetUserPassword(passwordTarget.id, values.password);
      message.success(`已重置 ${passwordTarget.name} 的密码`);
      setPasswordOpen(false);
    } catch (error) {
      if (error && typeof error === "object" && "errorFields" in error) return;
      message.error(errorMessage(error, "重置密码失败"));
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleDeactivate = (record: ManagedUser) => {
    if (me && record.id === me.id) {
      message.warning("不能停用当前登录账号");
      return;
    }
    modal.confirm({
      title: `停用用户「${record.name}」？`,
      content: "停用后该用户无法登录。项目与任务归属保留，可稍后重新启用。",
      okText: "停用",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await deactivateUser(record.id);
          message.success("用户已停用");
          retry();
        } catch (error) {
          message.error(errorMessage(error, "停用失败"));
          throw error;
        }
      },
    });
  };

  const handleReactivate = async (record: ManagedUser) => {
    try {
      await updateUser(record.id, { status: "ACTIVE" });
      message.success("用户已启用");
      retry();
    } catch (error) {
      message.error(errorMessage(error, "启用失败"));
    }
  };

  const handleSyncOa = async () => {
    setSyncingOa(true);
    try {
      const result = await syncUsersFromOa();
      message.success(
        `OA 同步完成：新建 ${result.created}，更新 ${result.updated}，跳过 ${result.skipped}（OA 在职 ${result.total_oa}）`,
      );
      retry();
    } catch (error) {
      message.error(errorMessage(error, "OA 同步失败（请确认已配置 OA MySQL）"));
    } finally {
      setSyncingOa(false);
    }
  };

  const columns: ColumnsType<ManagedUser> = [
      {
        title: "姓名",
        dataIndex: "name",
        key: "name",
        fixed: "left",
        width: 120,
      },
      {
        title: "用户名",
        dataIndex: "username",
        key: "username",
        width: 120,
      },
      {
        title: "来源",
        key: "source",
        width: 100,
        responsive: ["lg"],
        render: (_, record) =>
          record.oa_admin_id != null ? (
            <Tag color="blue">OA #{record.oa_admin_id}</Tag>
          ) : (
            <Tag>本地</Tag>
          ),
      },
      {
        title: "角色",
        dataIndex: "role",
        key: "role",
        width: 120,
        render: (role: string) => ROLE_LABELS[role] ?? role,
      },
      {
        title: "状态",
        dataIndex: "status",
        key: "status",
        width: 88,
        render: (status: string) => (
          <Tag color={status === "ACTIVE" ? "success" : "default"}>
            {STATUS_LABELS[status] ?? status}
          </Tag>
        ),
      },
      {
        title: "部门",
        dataIndex: "department",
        key: "department",
        width: 120,
        responsive: ["md"],
        render: (value: string | null) => value || "—",
      },
      {
        title: "邮箱",
        dataIndex: "email",
        key: "email",
        width: 180,
        ellipsis: true,
        responsive: ["lg"],
        render: (value: string | null) => value || "—",
      },
      {
        title: "手机",
        dataIndex: "mobile",
        key: "mobile",
        width: 120,
        responsive: ["lg"],
        render: (value: string | null) => value || "—",
      },
      {
        title: "操作",
        key: "actions",
        fixed: "right",
        width: isCompact ? 120 : 260,
        render: (_, record) => (
          <Space size={4} wrap>
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
              编辑
            </Button>
            {!isCompact ? (
              <Button
                type="link"
                size="small"
                icon={<KeyOutlined />}
                onClick={() => openPassword(record)}
              >
                改密
              </Button>
            ) : null}
            {record.status === "ACTIVE" ? (
              <Button
                type="link"
                size="small"
                danger
                icon={<StopOutlined />}
                disabled={me?.id === record.id}
                onClick={() => handleDeactivate(record)}
              >
                停用
              </Button>
            ) : (
              <Button
                type="link"
                size="small"
                icon={<CheckCircleOutlined />}
                onClick={() => handleReactivate(record)}
              >
                启用
              </Button>
            )}
            {isCompact ? (
              <Button
                type="link"
                size="small"
                icon={<KeyOutlined />}
                onClick={() => openPassword(record)}
              >
                改密
              </Button>
            ) : null}
          </Space>
        ),
      },
    ];

  if (!isAdmin) {
    return (
      <PageContainer>
        <PageHeader title="用户管理" subtitle="仅系统管理员可访问。" />
        <EmptyState title="无访问权限" description="请使用管理员账号登录后再试。" />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="用户管理"
        subtitle="身份来自 OA（osri_admin，只读）；本系统维护角色与业务权限。"
        action={
          <Space wrap>
            <Button
              icon={<CloudSyncOutlined />}
              loading={syncingOa}
              onClick={() => void handleSyncOa()}
            >
              从 OA 同步
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建用户
            </Button>
          </Space>
        }
      />

      {loading ? (
        <LoadingState tip="加载用户…" />
      ) : failed ? (
        <ErrorState description="无法获取用户列表，请稍后重试。" onRetry={retry} />
      ) : users.length === 0 ? (
        <EmptyState
          title="暂无用户"
          description="点击右上角新建第一个用户。"
          action={
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建用户
            </Button>
          }
        />
      ) : (
        <>
          <DataToolbar
            keyword={list.keyword}
            onKeywordChange={list.setKeyword}
            searchPlaceholder="搜索姓名 / 用户名 / 邮箱 / 部门"
            filters={FILTERS}
            filterValues={list.filters}
            onFilterChange={list.setFilter}
            onReset={list.reset}
            summary={`共 ${list.total} 个用户`}
          />

          {list.total === 0 ? (
            <EmptyState title="无匹配用户" description="试试调整搜索或筛选条件。" />
          ) : (
            <>
              <div className="app-card app-card--plain table-scroll">
                <Table<ManagedUser>
                  rowKey="id"
                  size="middle"
                  columns={columns}
                  dataSource={list.paged}
                  pagination={false}
                  scroll={{ x: isCompact ? 720 : 1100 }}
                />
              </div>
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
      )}

      <Modal
        title={editorMode === "create" ? "新建用户" : `编辑用户 · ${editing?.username ?? ""}`}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        destroyOnHidden
        okText="保存"
        cancelText="取消"
        width={560}
      >
        <Form form={editorForm} layout="vertical" requiredMark="optional" className="stack-sm">
          {editorMode === "create" ? (
            <>
              <Form.Item
                label="用户名"
                name="username"
                rules={[
                  { required: true, message: "请输入用户名" },
                  {
                    pattern: /^[a-zA-Z0-9_.-]+$/,
                    message: "仅支持字母、数字、._-",
                  },
                ]}
              >
                <Input autoComplete="off" placeholder="登录用户名" />
              </Form.Item>
              <Form.Item
                label="初始密码"
                name="password"
                rules={[
                  { required: true, message: "请输入密码" },
                  { min: 8, message: "至少 8 位" },
                ]}
              >
                <Input.Password autoComplete="new-password" />
              </Form.Item>
            </>
          ) : (
            <Typography.Paragraph type="secondary" className="meta-line">
              用户名不可修改：{editing?.username}
            </Typography.Paragraph>
          )}

          <Form.Item label="姓名" name="name" rules={[{ required: true, message: "请输入姓名" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="角色" name="role" rules={[{ required: true, message: "请选择角色" }]}>
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
          {editorMode === "edit" ? (
            <Form.Item label="状态" name="status" rules={[{ required: true }]}>
              <Select options={STATUS_OPTIONS} />
            </Form.Item>
          ) : null}
          <Form.Item label="部门" name="department">
            <Input />
          </Form.Item>
          <Form.Item label="邮箱" name="email" rules={[{ type: "email", message: "邮箱格式不正确" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="手机" name="mobile">
            <Input />
          </Form.Item>
          <Form.Item label="企业微信 UserId" name="wechat_user_id">
            <Input placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`重置密码 · ${passwordTarget?.name ?? ""}`}
        open={passwordOpen}
        onCancel={() => setPasswordOpen(false)}
        onOk={handlePasswordSave}
        confirmLoading={passwordSaving}
        destroyOnHidden
        okText="确认重置"
        cancelText="取消"
      >
        <Form form={passwordForm} layout="vertical" requiredMark="optional">
          <Form.Item
            label="新密码"
            name="password"
            rules={[
              { required: true, message: "请输入新密码" },
              { min: 8, message: "至少 8 位" },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            label="确认密码"
            name="confirm"
            dependencies={["password"]}
            rules={[
              { required: true, message: "请再次输入密码" },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue("password") === value) return Promise.resolve();
                  return Promise.reject(new Error("两次输入的密码不一致"));
                },
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
}

export default function UsersPage() {
  return (
    <RequireAuth>
      <UsersPageInner />
    </RequireAuth>
  );
}

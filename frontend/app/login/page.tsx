"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { App, Button, Divider, Form, Input } from "antd";
import { WechatOutlined } from "@ant-design/icons";

import { useAuth } from "@/components/providers/AuthProvider";
import { ApiError } from "@/lib/http";
import { APP_NAME } from "@/lib/env";
import { wecomLoginUrl } from "@/services/auth";

export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const { message } = App.useApp();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.replace("/my-tasks");
    }
  }, [loading, user, router]);

  if (!loading && user) {
    return null;
  }

  const onFinish = async (values: { username: string; password: string }) => {
    setSubmitting(true);
    try {
      await login(values);
      message.success("登录成功");
    } catch (error) {
      const detail =
        error instanceof ApiError &&
        typeof error.payload === "object" &&
        error.payload &&
        "detail" in error.payload
          ? String((error.payload as { detail: unknown }).detail)
          : "登录失败，请检查账号密码";
      message.error(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <section className="login-hero">
        <span className="login-hero__badge">{APP_NAME}</span>
        <h1 className="login-hero__title">{APP_NAME}</h1>
        <p className="login-hero__desc">
          每日一句话更新进展，管理层随时掌握项目风险与关键节点。
        </p>
      </section>

      <section className="login-form-wrap">
        <div className="login-card">
          <Form layout="vertical" onFinish={onFinish} requiredMark={false} size="large">
            <Form.Item
              label="用户名"
              name="username"
              rules={[{ required: true, message: "请输入用户名" }]}
            >
              <Input autoComplete="username" placeholder="admin / lisi / owner" />
            </Form.Item>
            <Form.Item
              label="密码"
              name="password"
              rules={[{ required: true, message: "请输入密码" }]}
            >
              <Input.Password autoComplete="current-password" placeholder="请输入密码" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting} size="large">
              登录
            </Button>
          </Form>

          <Divider plain className="login-divider">
            其他方式
          </Divider>

          <Button block size="large" icon={<WechatOutlined />} href={wecomLoginUrl()}>
            企业微信登录
          </Button>
        </div>
      </section>
    </div>
  );
}

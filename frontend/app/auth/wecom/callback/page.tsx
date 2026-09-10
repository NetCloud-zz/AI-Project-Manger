"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { App } from "antd";

import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { useAuth } from "@/components/providers/AuthProvider";
import { storeAuth } from "@/lib/auth-storage";
import { fetchMe } from "@/services/auth";

export default function WeComCallbackPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const { message } = App.useApp();
  const [statusText, setStatusText] = useState("正在完成企业微信登录…");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const error = params.get("error");
    const accessToken = params.get("access_token");

    if (error) {
      message.error(error);
      router.replace("/login");
      return;
    }

    if (!accessToken) {
      message.error("企业微信登录未完成，请重试");
      router.replace("/login");
      return;
    }

    const token = accessToken;
    let cancelled = false;

    async function completeLogin() {
      try {
        storeAuth(token, "");
        const user = await fetchMe();
        storeAuth(token, JSON.stringify(user));
        await refreshUser();
        if (!cancelled) {
          message.success("企业微信登录成功");
          router.replace("/my-tasks");
        }
      } catch {
        if (!cancelled) {
          setStatusText("登录失败");
          message.error("无法获取用户信息，请重新登录");
          router.replace("/login");
        }
      }
    }

    void completeLogin();

    return () => {
      cancelled = true;
    };
  }, [message, refreshUser, router]);

  return (
    <PageContainer width="form" flush>
      <LoadingState tip={statusText} />
    </PageContainer>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { App } from "antd";

import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { useAuth } from "@/components/providers/AuthProvider";
import { storeAuth } from "@/lib/auth-storage";
import { fetchMe } from "@/services/auth";

export default function OaCallbackPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const { message } = App.useApp();
  const [statusText, setStatusText] = useState("正在完成 OA 免登录…");

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
      message.error("OA 免登录未完成，请从 OA 重新进入");
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
          message.success("已通过 OA 登录");
          router.replace("/my-tasks");
        }
      } catch {
        if (!cancelled) {
          setStatusText("登录失败");
          message.error("无法获取用户信息，请重新从 OA 进入");
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

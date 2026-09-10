"use client";

import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import "dayjs/locale/zh-cn";
import type { ReactNode } from "react";

import { useViewport } from "@/hooks/useViewport";
import { desktopTheme, mobileTheme } from "@/lib/theme";

export function AntdProvider({ children }: { children: ReactNode }) {
  const viewport = useViewport();
  const theme = viewport === "mobile" ? mobileTheme : desktopTheme;

  return (
    <ConfigProvider locale={zhCN} theme={theme}>
      {children}
    </ConfigProvider>
  );
}

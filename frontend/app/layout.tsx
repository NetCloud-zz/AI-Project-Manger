import { AntdRegistry } from "@ant-design/nextjs-registry";
import type { Metadata, Viewport } from "next";

import { AppShell } from "@/components/layout/AppShell";
import { AntdProvider } from "@/components/providers/AntdProvider";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { APP_NAME } from "@/lib/env";
import "./globals.css";

export const metadata: Metadata = {
  title: APP_NAME,
  description: "面向多行业团队的轻量级 AI 项目管理 Agent",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0b5cab",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <AntdRegistry>
          <AntdProvider>
            <AuthProvider>
              <AppShell>{children}</AppShell>
            </AuthProvider>
          </AntdProvider>
        </AntdRegistry>
      </body>
    </html>
  );
}

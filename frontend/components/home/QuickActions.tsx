"use client";

import Link from "next/link";
import {
  DashboardOutlined,
  LoginOutlined,
  ProjectOutlined,
  RobotOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";

import { useAuth } from "@/components/providers/AuthProvider";

const GUEST_ACTIONS = [{ href: "/login", label: "登录", icon: LoginOutlined }] as const;

const AUTH_ACTIONS = [
  { href: "/my-tasks", label: "我的任务", icon: UnorderedListOutlined },
  { href: "/projects", label: "项目列表", icon: ProjectOutlined },
  { href: "/dashboard", label: "管理看板", icon: DashboardOutlined },
  { href: "/agent", label: "项目助手", icon: RobotOutlined },
] as const;

export function QuickActions() {
  const { user } = useAuth();
  const actions = user ? AUTH_ACTIONS : [...GUEST_ACTIONS, ...AUTH_ACTIONS];

  return (
    <div className="action-grid">
      {actions.map((item) => {
        const Icon = item.icon;
        return (
          <Link key={item.href} href={item.href} className="action-tile">
            <span className="action-tile__icon">
              <Icon />
            </span>
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}

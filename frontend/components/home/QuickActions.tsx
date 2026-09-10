"use client";

import Link from "next/link";
import {
  DashboardOutlined,
  LoginOutlined,
  ProjectOutlined,
  RobotOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";

const QUICK_ACTIONS = [
  { href: "/login", label: "登录", icon: LoginOutlined },
  { href: "/my-tasks", label: "我的任务", icon: UnorderedListOutlined },
  { href: "/projects", label: "项目列表", icon: ProjectOutlined },
  { href: "/dashboard", label: "管理看板", icon: DashboardOutlined },
  { href: "/agent", label: "项目助手", icon: RobotOutlined },
];

export function QuickActions() {
  return (
    <div className="action-grid">
      {QUICK_ACTIONS.map((item) => {
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

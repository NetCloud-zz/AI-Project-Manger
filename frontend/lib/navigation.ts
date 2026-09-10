import type { ComponentType } from "react";
import {
  BellOutlined,
  DashboardOutlined,
  HomeOutlined,
  ProjectOutlined,
  RobotOutlined,
  TeamOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";

import type { UserProfile } from "@/types/auth";

export type NavItem = {
  href: string;
  label: string;
  shortLabel?: string;
  icon: ComponentType;
};

const BASE_NAV: NavItem[] = [
  { href: "/", label: "首页", icon: HomeOutlined },
  { href: "/my-tasks", label: "我的任务", shortLabel: "任务", icon: UnorderedListOutlined },
  { href: "/projects", label: "项目", icon: ProjectOutlined },
];

export function getNavItems(user: UserProfile | null): NavItem[] {
  if (!user) return [];

  const canViewDashboard =
    user.role === "ADMIN" || user.role === "EXECUTIVE" || user.role === "PROJECT_OWNER";
  // PHASE F: all authenticated roles can open Project Assistant (tools still RBAC-gated).
  const canUseAgent = true;
  const canManageUsers = user.role === "ADMIN";

  return [
    ...BASE_NAV,
    ...(canViewDashboard
      ? [{ href: "/dashboard", label: "管理看板", shortLabel: "看板", icon: DashboardOutlined }]
      : []),
    ...(canUseAgent
      ? [{ href: "/agent", label: "项目助手", shortLabel: "助手", icon: RobotOutlined }]
      : []),
    { href: "/notifications", label: "通知中心", shortLabel: "通知", icon: BellOutlined },
    ...(canManageUsers
      ? [{ href: "/users", label: "用户管理", shortLabel: "用户", icon: TeamOutlined }]
      : []),
  ];
}

export function isNavActive(pathname: string, href: string): boolean {
  return pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));
}

export const ROLE_LABELS: Record<string, string> = {
  ADMIN: "系统管理员",
  EXECUTIVE: "管理层",
  PROJECT_OWNER: "项目负责人",
  MEMBER: "成员",
};

export const ROLE_OPTIONS = [
  { value: "ADMIN", label: ROLE_LABELS.ADMIN },
  { value: "EXECUTIVE", label: ROLE_LABELS.EXECUTIVE },
  { value: "PROJECT_OWNER", label: ROLE_LABELS.PROJECT_OWNER },
  { value: "MEMBER", label: ROLE_LABELS.MEMBER },
];

export const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "启用",
  INACTIVE: "停用",
};

export const STATUS_OPTIONS = [
  { value: "ACTIVE", label: STATUS_LABELS.ACTIVE },
  { value: "INACTIVE", label: STATUS_LABELS.INACTIVE },
];

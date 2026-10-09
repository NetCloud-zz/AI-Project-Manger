import type { ComponentType } from "react";
import {
  AppstoreOutlined,
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

const HOME: NavItem = { href: "/", label: "首页", icon: HomeOutlined };
const TASKS: NavItem = {
  href: "/my-tasks",
  label: "我的任务",
  shortLabel: "任务",
  icon: UnorderedListOutlined,
};
const PROJECTS: NavItem = { href: "/projects", label: "项目", icon: ProjectOutlined };
const AGENT: NavItem = {
  href: "/agent",
  label: "项目助手",
  shortLabel: "助手",
  icon: RobotOutlined,
};
const NOTIFICATIONS: NavItem = {
  href: "/notifications",
  label: "通知中心",
  shortLabel: "通知",
  icon: BellOutlined,
};
const DASHBOARD: NavItem = {
  href: "/dashboard",
  label: "管理看板",
  shortLabel: "看板",
  icon: DashboardOutlined,
};
const USERS: NavItem = {
  href: "/users",
  label: "用户管理",
  shortLabel: "用户",
  icon: TeamOutlined,
};

export const MORE_NAV_ITEM: NavItem = {
  href: "#more",
  label: "更多",
  shortLabel: "更多",
  icon: AppstoreOutlined,
};

export function getNavItems(user: UserProfile | null): NavItem[] {
  if (!user) return [];

  const canViewDashboard =
    user.role === "ADMIN" || user.role === "EXECUTIVE" || user.role === "PROJECT_OWNER";
  const canManageUsers = user.role === "ADMIN";

  return [
    HOME,
    TASKS,
    PROJECTS,
    ...(canViewDashboard ? [DASHBOARD] : []),
    AGENT,
    NOTIFICATIONS,
    ...(canManageUsers ? [USERS] : []),
  ];
}

/** Mobile bottom bar: at most five primary destinations. */
export function getMobilePrimaryNav(user: UserProfile | null): NavItem[] {
  if (!user) return [];
  return [TASKS, PROJECTS, AGENT, NOTIFICATIONS, MORE_NAV_ITEM];
}

/** Entries that live under the mobile “更多” sheet, respecting role. */
export function getMobileMoreNav(user: UserProfile | null): NavItem[] {
  if (!user) return [];
  const canViewDashboard =
    user.role === "ADMIN" || user.role === "EXECUTIVE" || user.role === "PROJECT_OWNER";
  const canManageUsers = user.role === "ADMIN";
  return [
    HOME,
    ...(canViewDashboard ? [DASHBOARD] : []),
    ...(canManageUsers ? [USERS] : []),
  ];
}

export function isNavActive(pathname: string, href: string): boolean {
  if (href === "#more") return false;
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

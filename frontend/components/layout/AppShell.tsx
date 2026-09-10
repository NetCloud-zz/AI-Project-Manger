"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { App, Button, Tooltip } from "antd";
import { LogoutOutlined } from "@ant-design/icons";

import { useAuth } from "@/components/providers/AuthProvider";
import { useViewport } from "@/hooks/useViewport";
import { APP_NAME } from "@/lib/env";
import { getNavItems, isNavActive, ROLE_LABELS } from "@/lib/navigation";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const viewport = useViewport();
  const isLogin = pathname === "/login";
  const isAuthCallback = pathname.startsWith("/auth/");
  const showChrome = Boolean(user) && !isLogin && !isAuthCallback;
  /* 768–1024px collapses the sidebar to icons, so labels move into tooltips. */
  const isRail = viewport === "tablet";

  const navItems = getNavItems(user);
  const initials = user?.name?.slice(0, 1) ?? "?";
  const roleLabel = user ? (ROLE_LABELS[user.role] ?? user.role) : "";

  if (!showChrome) {
    return (
      <App>
        <div className="app-shell">
          <div className="app-main--full">{children}</div>
        </div>
      </App>
    );
  }

  return (
    <App>
      <div className="app-shell app-shell--auth">
        <aside className="app-sidebar" aria-label="侧边导航">
          <Link href="/" className="app-sidebar__brand">
            <span className="app-sidebar__label">{APP_NAME}</span>
          </Link>

          <nav className="app-sidebar__nav">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = isNavActive(pathname, item.href);
              return (
                <Tooltip key={item.href} title={isRail ? item.label : null} placement="right">
                  <Link
                    href={item.href}
                    className={`app-sidebar__link${active ? " app-sidebar__link--active" : ""}`}
                  >
                    <span className="app-sidebar__icon">
                      <Icon />
                    </span>
                    <span className="app-sidebar__label">{item.label}</span>
                  </Link>
                </Tooltip>
              );
            })}
          </nav>

          <div className="app-sidebar__footer">
            <div className="app-sidebar__user">
              <div className="app-avatar" aria-hidden>
                {initials}
              </div>
              <div className="app-sidebar__user-meta app-sidebar__label">
                <div className="app-sidebar__username">{user?.name}</div>
                <div className="app-sidebar__role">{roleLabel}</div>
              </div>
            </div>
            <Tooltip title={isRail ? "退出登录" : null} placement="right">
              <Button
                type="text"
                size="small"
                icon={<LogoutOutlined />}
                onClick={logout}
                aria-label="退出登录"
              >
                <span className="app-sidebar__label">退出</span>
              </Button>
            </Tooltip>
          </div>
        </aside>

        <div className="app-shell__body">
          <header className="app-header">
            <div className="app-header__brand">{APP_NAME}</div>
            <div className="app-header__user">
              <div className="app-avatar" aria-hidden>
                {initials}
              </div>
              <Button
                type="text"
                size="small"
                icon={<LogoutOutlined />}
                onClick={logout}
                aria-label="退出登录"
              />
            </div>
          </header>

          <div className="app-main">{children}</div>
        </div>

        <nav className="app-tabbar" aria-label="主导航">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isNavActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`app-tabbar__item${active ? " app-tabbar__item--active" : ""}`}
              >
                <span className="app-tabbar__icon">
                  <Icon />
                </span>
                <span className="app-tabbar__label">{item.shortLabel ?? item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </App>
  );
}

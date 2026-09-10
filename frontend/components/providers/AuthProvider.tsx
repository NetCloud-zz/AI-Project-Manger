"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { clearAuth, getStoredToken, getStoredUserJson, storeAuth } from "@/lib/auth-storage";
import { setAuthTokenOverride } from "@/lib/http";
import { fetchMe, login as loginRequest } from "@/services/auth";
import type { LoginRequest, UserProfile } from "@/types/auth";

interface AuthContextValue {
  user: UserProfile | null;
  token: string | null;
  loading: boolean;
  login: (body: LoginRequest) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const applySession = useCallback((nextToken: string | null, nextUser: UserProfile | null) => {
    setToken(nextToken);
    setUser(nextUser);
    setAuthTokenOverride(nextToken);
  }, []);

  const refreshUser = useCallback(async () => {
    const activeToken = getStoredToken();
    if (!activeToken) {
      applySession(null, null);
      return;
    }
    const profile = await fetchMe();
    applySession(activeToken, profile);
    storeAuth(activeToken, JSON.stringify(profile));
  }, [applySession]);

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const storedToken = getStoredToken();
        const storedUser = getStoredUserJson();
        if (!storedToken) {
          applySession(null, null);
          return;
        }
        applySession(storedToken, storedUser ? (JSON.parse(storedUser) as UserProfile) : null);
        await refreshUser();
      } catch {
        clearAuth();
        applySession(null, null);
      } finally {
        setLoading(false);
      }
    };
    void bootstrap();
  }, [applySession, refreshUser]);

  const login = useCallback(
    async (body: LoginRequest) => {
      const result = await loginRequest(body);
      storeAuth(result.access_token, JSON.stringify(result.user));
      applySession(result.access_token, result.user);
      router.push("/my-tasks");
    },
    [applySession, router],
  );

  const logout = useCallback(() => {
    clearAuth();
    applySession(null, null);
    router.push("/login");
  }, [applySession, router]);

  const value = useMemo(
    () => ({ user, token, loading, login, logout, refreshUser }),
    [user, token, loading, login, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

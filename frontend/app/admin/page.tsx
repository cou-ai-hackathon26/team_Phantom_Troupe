"use client";

import { useCallback, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Dashboard } from "@/components/admin/dashboard";
import { LoginForm } from "@/components/admin/login-form";
import type { AdminInfo } from "@/components/admin/shared";
import { adminCheck } from "@/lib/api";

const TOKEN_KEY = "adhikarai.adminToken";

function readToken(): string {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveToken(token: string | null) {
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the admin signs in again after a reload */
  }
}

export default function AdminPage() {
  const [token, setToken] = useState<string | null>(null);
  const [info, setInfo] = useState<AdminInfo | null>(null);
  const [checking, setChecking] = useState(true); // restoring a saved session

  useEffect(() => {
    const saved = readToken();
    if (!saved) {
      setChecking(false);
      return;
    }
    adminCheck(saved)
      .then((res) => {
        setToken(saved);
        setInfo(res);
      })
      .catch(() => saveToken(null))
      .finally(() => setChecking(false));
  }, []);

  const logout = useCallback(() => {
    saveToken(null);
    setToken(null);
    setInfo(null);
  }, []);

  if (checking) {
    return (
      <main className="flex min-h-[calc(100dvh-4rem)] items-center justify-center">
        <LoaderCircle className="size-6 animate-spin text-primary" aria-label="লোড হচ্ছে" />
      </main>
    );
  }
  if (!token) {
    return (
      <LoginForm
        onLogin={(t, res) => {
          saveToken(t);
          setToken(t);
          setInfo(res);
        }}
      />
    );
  }
  return <Dashboard token={token} info={info} onLogout={logout} />;
}

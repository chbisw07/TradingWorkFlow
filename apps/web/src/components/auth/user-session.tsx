"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import type { CurrentUser } from "../../lib/current-user";

const UserContext = createContext<CurrentUser | null>(null);

export function UserSession({
  user,
  children,
}: {
  user: CurrentUser;
  children: ReactNode;
}) {
  const router = useRouter();
  useEffect(() => {
    let active = true;
    async function verify() {
      try {
        const response = await fetch("/api/v1/auth/me", { cache: "no-store" });
        if (active && response.status === 401) {
          router.replace("/login");
          router.refresh();
        }
      } catch {
        /* Network loss is not proof of session expiration. */
      }
    }
    const interval = window.setInterval(verify, 60000);
    window.addEventListener("focus", verify);
    window.addEventListener("pageshow", verify);
    return () => {
      active = false;
      clearInterval(interval);
      window.removeEventListener("focus", verify);
      window.removeEventListener("pageshow", verify);
    };
  }, [router]);
  return <UserContext.Provider value={user}>{children}</UserContext.Provider>;
}

export function UserMenu() {
  const user = useContext(UserContext);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  async function logout() {
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/v1/auth/logout", { method: "POST" });
      if (!response.ok) throw new Error();
      router.replace("/login");
      router.refresh();
    } catch {
      setError("Unable to sign out. Please try again.");
      setPending(false);
    }
  }
  return (
    <div className="user-menu">
      <span className="current-user" title={user?.username}>
        {user?.display_name || "Not signed in"}
      </span>
      {user && (
        <button type="button" onClick={logout} disabled={pending}>
          {pending ? "Signing out…" : "Sign out"}
        </button>
      )}
      {error && <span role="alert">{error}</span>}
    </div>
  );
}

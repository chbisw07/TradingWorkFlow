"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ThemeToggle } from "../shell/theme-toggle";

export function LoginForm() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: data.get("username"),
          password: data.get("password"),
        }),
      });
      if (!response.ok) {
        setError(
          response.status === 401 || response.status === 422
            ? "Unable to sign in. Check your username and password."
            : "Sign-in is unavailable. Please try again.",
        );
        setPending(false);
        return;
      }
      form.reset();
      router.replace("/");
      router.refresh();
    } catch {
      setError("Sign-in is unavailable. Please try again.");
      setPending(false);
    }
  }
  return (
    <main className="login-page">
      <div className="login-brand">
        <span className="brand-mark" aria-hidden="true">
          twf<span>.</span>
        </span>
        <span>TradingWorkFlow</span>
        <ThemeToggle />
      </div>
      <div className="login-layout">
        <section className="login-intro" aria-labelledby="login-intro-title">
          <p className="eyebrow">YOUR TRADING WORKSPACE</p>
          <h1 id="login-intro-title">Clarity before action.</h1>
          <p>One place to bring your trading workflow into focus.</p>
          <p className="login-footnote">
            Application access only. Broker connections and trading approvals
            remain separate.
          </p>
        </section>
        <section className="login-card" aria-labelledby="login-title">
          <p className="eyebrow">WELCOME BACK</p>
          <h2 id="login-title">Sign in to TWF</h2>
          <p>Use your application username and password.</p>
          <form onSubmit={login} aria-busy={pending}>
            <label htmlFor="username">Username</label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
              minLength={3}
              maxLength={64}
              disabled={pending}
            />
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={128}
              disabled={pending}
            />
            {error && (
              <p className="login-error" role="alert">
                {error}
              </p>
            )}
            <button type="submit" disabled={pending}>
              {pending ? "Signing in…" : "Sign in"}
            </button>
            {pending && <span role="status">Verifying your credentials…</span>}
          </form>
        </section>
      </div>
    </main>
  );
}

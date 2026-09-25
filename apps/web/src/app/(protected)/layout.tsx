import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { fetchCurrentUser } from "../../lib/auth-server";
import { UserSession } from "../../components/auth/user-session";
import { AppShell } from "../../components/shell/app-shell";

export default async function ProtectedLayout({
  children,
}: {
  children: ReactNode;
}) {
  const user = await fetchCurrentUser();
  if (!user) redirect("/login");
  return (
    <UserSession user={user}>
      <AppShell>{children}</AppShell>
    </UserSession>
  );
}

import { redirect } from "next/navigation";
import { LoginForm } from "../../components/auth/login-form";
import { fetchCurrentUser } from "../../lib/auth-server";

export default async function LoginPage() {
  if (await fetchCurrentUser()) redirect("/");
  return <LoginForm />;
}

import { redirect } from "next/navigation";

export default async function OrdersPage({
  searchParams,
}: {
  searchParams: Promise<{ selected?: string | string[] }>;
}) {
  const selected = (await searchParams).selected;
  const id =
    typeof selected === "string" && /^[0-9a-f-]{36}$/i.test(selected)
      ? selected
      : null;
  redirect(`/trade/orders${id ? `?selected=${encodeURIComponent(id)}` : ""}`);
}

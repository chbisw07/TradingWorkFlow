import { notFound } from "next/navigation";
import { OrdersWorkspace } from "../../../../components/orders/orders-workspace";

export default async function TradePage({
  params,
}: {
  params: Promise<{ section?: string[] }>;
}) {
  const { section = [] } = await params;
  if (
    section.length > 1 ||
    (section[0] && !["orders", "queue", "positions"].includes(section[0]))
  )
    notFound();
  return <OrdersWorkspace />;
}

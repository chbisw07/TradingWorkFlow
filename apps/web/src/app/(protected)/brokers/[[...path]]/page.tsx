import { BrokerWorkspace } from "../../../../components/brokers/broker-workspace";
export default async function BrokersPage({
  params,
}: {
  params: Promise<{ path?: string[] }>;
}) {
  const { path = [] } = await params;
  return <BrokerWorkspace path={path} />;
}

import { InstrumentSearch } from "../../../../components/brokers/instrument-search";
import { notFound } from "next/navigation";
import { BrokerWorkspace } from "../../../../components/brokers/broker-workspace";
import { brokerViews, type BrokerView } from "../../../../lib/brokers";

export default async function BrokersPage({
  params,
}: {
  params: Promise<{ path?: string[] }>;
}) {
  const { path = [] } = await params;
  if (
    path.length === 2 &&
    /^[0-9a-f-]{36}$/i.test(path[0]) &&
    path[1] === "instruments"
  )
    return <InstrumentSearch key={path[0]} accountId={path[0]} />;
  if (path.length === 0) return <BrokerWorkspace key="overview" />;
  if (
    path.length !== 2 ||
    !/^[0-9a-f-]{36}$/i.test(path[0]) ||
    !brokerViews.includes(path[1] as BrokerView)
  )
    notFound();
  return (
    <BrokerWorkspace
      key={path.join("/")}
      accountId={path[0]}
      view={path[1] as BrokerView}
    />
  );
}

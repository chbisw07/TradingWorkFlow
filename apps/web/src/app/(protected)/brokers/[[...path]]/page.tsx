import { BrokerLinks } from "../../../../components/brokers/broker-navigation";
import {
  RealBrokerRoom,
  BrokerRoster,
} from "../../../../components/brokers/real-broker-room";
import { RealBrokers } from "../../../../components/brokers/real-brokers";
import { roomViews, type RoomView } from "../../../../lib/portfolio";
import { notFound } from "next/navigation";
import { BrokerWorkspace } from "../../../../components/brokers/broker-workspace";
import { brokerViews, type BrokerView } from "../../../../lib/brokers";

export default async function BrokersPage({
  params,
}: {
  params: Promise<{ path?: string[] }>;
}) {
  const { path = [] } = await params;
  if (path.length === 1 && path[0] === "manage")
    return (
      <div className="broker-room">
        <BrokerLinks active="manage" />
        <h1>Manage Brokers</h1>
        <RealBrokers />
      </div>
    );
  if (path.length === 1 && path[0] === "zerodha")
    return (
      <div className="broker-room">
        <BrokerRoster landing />
      </div>
    );
  if (
    path.length === 3 &&
    path[0] === "zerodha" &&
    /^[0-9a-f-]{36}$/i.test(path[1]) &&
    roomViews.includes(path[2] as RoomView)
  )
    return (
      <RealBrokerRoom
        key={path[1]}
        accountId={path[1]}
        view={path[2] as RoomView}
      />
    );
  if (
    path.length === 2 &&
    /^[0-9a-f-]{36}$/i.test(path[0]) &&
    path[1] === "instruments"
  )
    return (
      <RealBrokerRoom key={path[0]} accountId={path[0]} view="instruments" />
    );
  if (path.length === 0)
    return (
      <div className="broker-room">
        <BrokerLinks />
        <h1>Brokers</h1>
        <BrokerRoster />
      </div>
    );
  if (path.length === 1 && path[0] === "development")
    return <BrokerWorkspace key="development" />;
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

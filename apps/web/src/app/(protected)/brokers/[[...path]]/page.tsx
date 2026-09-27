import { RealBrokerRoom } from "../../../../components/brokers/real-broker-room";
import {
  RealBrokers,
  BrokerRoster,
  BrokerSetup,
} from "../../../../components/brokers/real-brokers";
import { resolveBrokerRoom } from "../../../../lib/broker-room-routes";
import { notFound } from "next/navigation";
import { BrokerWorkspace } from "../../../../components/brokers/broker-workspace";
import { brokerViews, type BrokerView } from "../../../../lib/brokers";

export default async function BrokersPage({
  params,
}: {
  params: Promise<{ path?: string[] }>;
}) {
  const { path = [] } = await params;
  if (path[0] === "manage") {
    if (path.length === 1 || (path.length === 2 && path[1] === "my"))
      return (
        <RealBrokers
          key={path.join("/")}
          view={path[1] === "my" ? "my" : "all"}
        />
      );
    if (path.length === 3 && path[1] === "setup")
      return <BrokerSetup key={path.join("/")} providerId={path[2]} />;
    if (
      path.length === 3 &&
      path[1] === "accounts" &&
      /^[0-9a-f-]{36}$/i.test(path[2])
    )
      return <BrokerSetup key={path.join("/")} accountId={path[2]} />;
    notFound();
  }
  if (path.length === 1 && path[0] === "zerodha")
    return (
      <div className="broker-room">
        <h1>Brokers</h1>
        <BrokerRoster />
      </div>
    );
  const room = resolveBrokerRoom(path);
  if (room)
    return (
      <RealBrokerRoom
        key={room.accountId}
        accountId={room.accountId}
        view={room.view}
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

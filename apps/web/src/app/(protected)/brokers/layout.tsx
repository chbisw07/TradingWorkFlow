import type { ReactNode } from "react";
import { BrokerSession } from "../../../components/brokers/broker-session";
import { BrokerLinks } from "../../../components/brokers/broker-navigation";
import { brokerDevToolsEnabled } from "../../../lib/broker-environment";
export default function BrokersLayout({ children }: { children: ReactNode }) {
  return (
    <BrokerSession
      development={brokerDevToolsEnabled(
        process.env.TWF_ENVIRONMENT,
        process.env.NODE_ENV,
      )}
    >
      <BrokerLinks />
      {children}
    </BrokerSession>
  );
}

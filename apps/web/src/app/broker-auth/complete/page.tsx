import type { Metadata } from "next";
import { BrokerAuthComplete } from "../../../components/brokers/broker-auth-complete";
export const metadata: Metadata = {
  title: "Verify Zerodha | TradingWorkFlow",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};
export default function CompletePage() {
  return <BrokerAuthComplete />;
}

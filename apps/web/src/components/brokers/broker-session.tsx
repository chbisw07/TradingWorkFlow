"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  brokerAuthRequest,
  type Connection,
} from "../../lib/broker-connections";
const BrokerContext = createContext<{
  connections: Connection[] | null;
  error: string;
  reload: () => Promise<Connection[]>;
  development: boolean;
  observedAt: number;
} | null>(null);
export function BrokerSession({
  children,
  development = false,
}: {
  children: ReactNode;
  development?: boolean;
}) {
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [error, setError] = useState("");
  const [observedAt, setObservedAt] = useState(0);
  const sequence = useRef(0);
  const reload = useCallback(async () => {
    const request = ++sequence.current;
    try {
      const values: Connection[] = await brokerAuthRequest("accounts");
      if (request === sequence.current) {
        setObservedAt(performance.now());
        setConnections(values);
        setError("");
      }
      return values;
    } catch {
      if (request === sequence.current) {
        setObservedAt(performance.now());
        setConnections(null);
        setError("Broker connections are unavailable. Refresh to try again.");
      }
      return [];
    }
  }, []);
  const invalidate = useCallback(() => {
    ++sequence.current;
  }, []);
  useEffect(() => {
    const refresh = () => {
      void reload();
    };
    refresh();
    window.addEventListener("focus", refresh);
    return () => {
      invalidate();
      window.removeEventListener("focus", refresh);
    };
  }, [reload, invalidate]);
  return (
    <BrokerContext.Provider
      value={{ connections, error, reload, development, observedAt }}
    >
      {children}
    </BrokerContext.Provider>
  );
}
export function useBrokerSession() {
  const session = useContext(BrokerContext);
  if (!session) throw new Error("BrokerSession is required");
  return session;
}
export function ConnectionLoadState() {
  const { error, connections, reload } = useBrokerSession();
  if (error)
    return (
      <p role="alert">
        {error}{" "}
        <button className="quiet-button" onClick={() => void reload()}>
          Refresh connections
        </button>
      </p>
    );
  if (connections === null)
    return <p role="status">Loading broker connections…</p>;
  return null;
}

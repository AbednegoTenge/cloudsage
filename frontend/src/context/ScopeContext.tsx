import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { AwsConnection } from "../types/domain";

interface Scope {
  connections: AwsConnection[];
  connection: AwsConnection | undefined;
  region: string;
  setConnectionId: (id: string) => void;
  setRegion: (r: string) => void;
  refreshConnections: () => Promise<void>;
}

const ScopeContext = createContext<Scope | null>(null);

/** The AWS account + region every investigation is bound to. */
export function ScopeProvider({ children }: { children: ReactNode }) {
  const [connections, setConnections] = useState<AwsConnection[]>([]);
  const [connectionId, setConnectionId] = useState<string>();
  const [region, setRegion] = useState("");

  const refreshConnections = async () => setConnections(await api.listConnections());
  useEffect(() => {
    void refreshConnections();
  }, []);

  const connection = connections.find((c) => c.id === connectionId) ?? connections.find((c) => c.status === "connected") ??
    connections.find((c) => c.status !== "error");

  useEffect(() => {
    if (connection && !connection.allowedRegions.includes(region)) setRegion(connection.defaultRegion);
  }, [connection, region]);

  const value = useMemo<Scope>(
    () => ({ connections, connection, region, setConnectionId, setRegion, refreshConnections }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [connections, connection, region],
  );
  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useScope(): Scope {
  const ctx = useContext(ScopeContext);
  if (!ctx) throw new Error("useScope must be used inside ScopeProvider");
  return ctx;
}

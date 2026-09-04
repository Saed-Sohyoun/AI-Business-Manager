/**
 * Data mode: demo (fixtures) vs live (backend only).
 * Never fall back to demo data when a live request fails.
 * Live works with session auth or emergency API key.
 */

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { hasOwnerApiKeyConfigured } from "../api/client.js";

const STORAGE_KEY = "bos.dataMode";

function readInitialMode() {
  const env = (import.meta.env.VITE_DATA_MODE || "").toLowerCase();
  if (env === "demo" || env === "live") return env;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "demo" || stored === "live") return stored;
  } catch {
    /* ignore */
  }
  // Default: live when emergency key present; otherwise demo for local browsing.
  // Session auth is gated separately — owners can switch to live and sign in.
  return hasOwnerApiKeyConfigured() ? "live" : "demo";
}

const DataModeContext = createContext(null);

export function DataModeProvider({ children }) {
  const [mode, setModeState] = useState(readInitialMode);

  const setMode = useCallback((next) => {
    const value = next === "live" ? "live" : "demo";
    setModeState(value);
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch {
      /* ignore */
    }
  }, []);

  const hasOwnerKey = hasOwnerApiKeyConfigured();
  const hasLiveAuthCapable = hasOwnerKey;

  const value = useMemo(
    () => ({
      mode,
      isDemo: mode === "demo",
      isLive: mode === "live",
      setMode,
      /** @deprecated Prefer hasLiveAuthCapable; kept for existing callers */
      hasOwnerKey,
      /** Emergency API key present — session auth is handled by AuthContext */
      hasLiveAuthCapable,
    }),
    [mode, setMode, hasOwnerKey, hasLiveAuthCapable],
  );

  return <DataModeContext.Provider value={value}>{children}</DataModeContext.Provider>;
}

export function useDataMode() {
  const ctx = useContext(DataModeContext);
  if (!ctx) throw new Error("useDataMode requires DataModeProvider");
  return ctx;
}

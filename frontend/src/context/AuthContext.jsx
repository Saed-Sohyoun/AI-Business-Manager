/**
 * Owner session auth — cookie session + CSRF in sessionStorage.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as ownerApi from "../api/owner.js";
import {
  clearStoredCsrfToken,
  hasOwnerApiKeyConfigured,
  setStoredCsrfToken,
} from "../api/client.js";

const AuthContext = createContext(null);

function applyCsrfFromPayload(payload) {
  if (payload?.csrf_token) {
    setStoredCsrfToken(payload.csrf_token);
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const me = await ownerApi.getMe();
      applyCsrfFromPayload(me);
      setUser({
        email: me.email,
        displayName: me.display_name || me.email,
        authMethod: me.auth_method || "session",
      });
      return me;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(async (email, password) => {
    const result = await ownerApi.login({ email, password });
    applyCsrfFromPayload(result);
    setUser({
      email: result.email,
      displayName: result.display_name || result.email,
      authMethod: "session",
    });
    return result;
  }, []);

  const logout = useCallback(async () => {
    try {
      await ownerApi.logout();
    } catch {
      /* still clear local session */
    }
    clearStoredCsrfToken();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      isAuthenticated: Boolean(user),
      /** Live API access via session or emergency API key */
      canUseLiveApi: Boolean(user) || hasOwnerApiKeyConfigured(),
      login,
      logout,
      refresh,
    }),
    [user, loading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth requires AuthProvider");
  return ctx;
}

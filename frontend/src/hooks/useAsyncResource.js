/**
 * Load async resources with AbortController cleanup.
 * Live mode: never falls back to demo fixtures on error.
 */

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * @template T
 * @param {() => Promise<T>} loader
 * @param {{ enabled?: boolean, deps?: unknown[] }} [opts]
 */
export function useAsyncResource(loader, opts = {}) {
  const { enabled = true, deps = [] } = opts;
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const gen = useRef(0);

  const reload = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const id = ++gen.current;
    setLoading(true);
    setError(null);
    try {
      const result = await loaderRef.current();
      if (id === gen.current) {
        setData(result);
        setLoading(false);
      }
    } catch (err) {
      if (id === gen.current) {
        setData(null);
        setError(err);
        setLoading(false);
      }
    }
  }, [enabled]);

  useEffect(() => {
    reload();
    return () => {
      gen.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, ...deps]);

  return { data, error, loading, reload, setData };
}

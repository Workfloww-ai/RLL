import { useState, useEffect, useRef } from 'react';
import { apiFetchCached, getCachedSnapshot, getAuthToken } from '../lib/api';
import { logger } from '../lib/logger';

export interface UseMobileSWROptions<T> {
  ttlMs?: number;
  initialData?: T;
  enabled?: boolean;
}

export interface UseMobileSWRResult<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  isRevalidating: boolean;
  mutate: () => Promise<void>;
}

/**
 * Custom React Hook providing Stale-While-Revalidate (SWR) behavior for Mobile Apps.
 * Features:
 * - 0ms Instantaneous Mounting: Instantly renders cached snapshot from memory/disk if available.
 * - Silent Background Revalidation: Fires a non-blocking network request to fetch fresh server data.
 * - Zero Loading Spinner Delays on repeat screen mounts.
 */
export function useMobileSWR<T = unknown>(
  endpointPath: string | null,
  options: UseMobileSWROptions<T> = {}
): UseMobileSWRResult<T> {
  const { ttlMs = 60_000, initialData = null, enabled = true } = options;

  // 1. Check synchronous snapshot for instant 0ms mounting
  const [data, setData] = useState<T | null>(() => {
    if (!endpointPath || !enabled) return initialData;
    const snapshot = getCachedSnapshot<T>(endpointPath);
    return snapshot !== null ? snapshot : initialData;
  });

  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(() => data === null && enabled);
  const [isRevalidating, setIsRevalidating] = useState<boolean>(false);
  const mountedRef = useRef(true);

  const fetchAndRevalidate = async () => {
    if (!endpointPath || !enabled) return;

    if (data !== null) {
      setIsRevalidating(true);
    } else {
      setLoading(true);
    }

    try {
      const token = await getAuthToken();
      const freshData = (await apiFetchCached(endpointPath, ttlMs, token || undefined)) as T;

      if (mountedRef.current && freshData !== undefined) {
        const isDifferent = JSON.stringify(data) !== JSON.stringify(freshData);
        if (isDifferent || data === null) {
          setData(freshData);
        }
        setError(null);
      }
    } catch (err: any) {
      if (mountedRef.current) {
        logger.warn(`useMobileSWR error on ${endpointPath}:`, err);
        setError(err instanceof Error ? err : new Error(String(err)));
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
        setIsRevalidating(false);
      }
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    fetchAndRevalidate();

    return () => {
      mountedRef.current = false;
    };
  }, [endpointPath, enabled]);

  return {
    data,
    error,
    loading,
    isRevalidating,
    mutate: fetchAndRevalidate,
  };
}

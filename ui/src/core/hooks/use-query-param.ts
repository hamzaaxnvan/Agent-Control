import { useRouter } from 'next/router';
import { useCallback, useMemo, useRef } from 'react';

type UseQueryParamOptions = {
  /** Default value when param is not in URL */
  defaultValue?: string;
  /** Whether to use shallow routing (no data fetching, default: true) */
  shallow?: boolean;
};

/**
 * Sync a state value with a URL query parameter.
 * Enables shareable URLs and preserves state on refresh/back navigation.
 *
 * @param key - The query parameter key (e.g., "search" for ?search=value)
 * @param options - Configuration options
 * @returns [value, setValue] - Similar to useState, but synced with URL
 *
 * @example
 * const [search, setSearch] = useQueryParam("search");
 * // URL: /agents?search=hello
 * // search = "hello"
 */
export function useQueryParam(
  key: string,
  options: UseQueryParamOptions = {}

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

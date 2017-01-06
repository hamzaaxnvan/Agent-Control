import type { TextInputProps } from '@mantine/core';
import { TextInput } from '@mantine/core';
import { IconSearch, IconX } from '@tabler/icons-react';
import { useMemo } from 'react';

import { useQueryParam } from '@/core/hooks/use-query-param';

type SearchInputProps = {
  /** Query parameter key to sync with URL (e.g., "search", "q", "store_q") */
  queryKey: string;
} & Omit<TextInputProps, 'value' | 'onChange' | 'leftSection' | 'rightSection'>;

/**
 * Reusable search input component that syncs with URL query parameters.
 * Includes a clear button (X icon) when there's text.
 * Accepts all TextInput props for full customization.
 *
 * @example
 * <SearchInput queryKey="search" placeholder="Search agents..." w={250} />
 */
export function SearchInput({
  queryKey,
  placeholder = 'Search...',
  w = 250,
  ...rest
}: SearchInputProps) {
  const [searchQuery, setSearchQuery] = useQueryParam(queryKey);


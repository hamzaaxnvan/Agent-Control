import { useEffect, useRef } from 'react';

type UseInfiniteScrollOptions = {
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
};

/**
 * Custom hook for infinite scroll with IntersectionObserver.
 * Works inside ScrollArea components by using a ref for the scroll container.
 *
 * @returns sentinelRef - attach to a div at the bottom of scrollable content
 * @returns scrollContainerRef - attach to ScrollArea's viewportRef
 *
 * @example
 * const { sentinelRef, scrollContainerRef } = useInfiniteScroll({
 *   hasNextPage,

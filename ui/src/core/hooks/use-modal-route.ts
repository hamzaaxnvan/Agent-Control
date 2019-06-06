import { useRouter } from 'next/router';
import { useCallback, useMemo } from 'react';

import { SUBMODAL_NAMES } from '@/core/constants/modal-routes';

/**
 * Hook to manage modal state via URL query parameters
 *
 * URL structure:
 * - ?modal=control-store - Opens Control Store modal
 * - ?modal=control-store&submodal=add-new - Opens Control Store with Add New Control modal
 * - ?modal=control-store&submodal=create&evaluator=regex - Opens Control Store with Create Control modal
 * - ?modal=control-store&submodal=edit&controlId=123 - Opens Control Store with Edit Control modal
 * - ?modal=edit&controlId=123 - Opens Edit Control modal directly (from agent detail page)
 */
export function useModalRoute() {
  const router = useRouter();
  const { modal, submodal, evaluator, controlId } = router.query;

  const modalState = useMemo(() => {
    return {
      modal: typeof modal === 'string' ? modal : null,
      submodal: typeof submodal === 'string' ? submodal : null,

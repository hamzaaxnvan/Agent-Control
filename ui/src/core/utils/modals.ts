import { modals } from '@mantine/modals';
import type { ReactNode } from 'react';

const CONFIRM_BTN_CLASS = 'confirm-modal-confirm-btn';
const CONFIRM_MODAL_DEFAULTS = {
  size: 'sm',
  centered: true,
  cancelProps: { variant: 'default', size: 'sm' },
};

export type ConfirmModalOptions = {
  title: string;
  children: ReactNode;
  onConfirm: () => void;
  onCancel?: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
};

/**
 * Open a standard (non-destructive) confirmation modal.
 *
 * Returns the modal id, which can be used to close it programmatically if needed.
 */
export function openActionConfirmModal({

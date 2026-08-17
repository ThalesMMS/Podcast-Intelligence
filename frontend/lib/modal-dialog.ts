export interface ModalDialogElement {
  close: () => void;
  open: boolean;
  showModal: () => void;
}

export interface FocusTarget {
  focus: () => void;
  getClientRects?: () => ArrayLike<unknown>;
  isConnected?: boolean;
}

export function activateModalDialog(dialog: ModalDialogElement, initialFocus: FocusTarget) {
  if (!dialog.open) dialog.showModal();
  initialFocus.focus();
  return () => {
    if (dialog.open) dialog.close();
  };
}

export function handleModalCancel(event: Pick<Event, "preventDefault">, closeDialog: () => void) {
  event.preventDefault();
  closeDialog();
}

export function restoreModalTriggerFocus(
  trigger: FocusTarget | null,
  fallback: FocusTarget | null,
  schedule: (callback: () => void) => void,
) {
  schedule(() => {
    const target = isVisibleFocusTarget(trigger) ? trigger : fallback;
    if (isVisibleFocusTarget(target)) target.focus();
  });
}

function isVisibleFocusTarget(target: FocusTarget | null): target is FocusTarget {
  return Boolean(
    target &&
    target.isConnected !== false &&
    (target.getClientRects === undefined || target.getClientRects().length > 0),
  );
}

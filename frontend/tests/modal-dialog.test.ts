import { describe, expect, it, vi } from "vitest";

import {
  activateModalDialog,
  handleModalCancel,
  restoreModalTriggerFocus,
} from "../lib/modal-dialog";

describe("modal dialog lifecycle", () => {
  it("opens modally, focuses the name field and closes during cleanup", () => {
    const dialog = {
      open: false,
      showModal: vi.fn(function (this: { open: boolean }) {
        this.open = true;
      }),
      close: vi.fn(function (this: { open: boolean }) {
        this.open = false;
      }),
    };
    const input = { focus: vi.fn() };

    const cleanup = activateModalDialog(dialog, input);

    expect(dialog.showModal).toHaveBeenCalledOnce();
    expect(input.focus).toHaveBeenCalledOnce();
    cleanup();
    expect(dialog.close).toHaveBeenCalledOnce();
  });

  it("prevents native cancellation before closing through application state", () => {
    const event = { preventDefault: vi.fn() };
    const closeDialog = vi.fn();

    handleModalCancel(event, closeDialog);

    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(closeDialog).toHaveBeenCalledOnce();
  });

  it("restores focus to a connected trigger or the transcript fallback", () => {
    const connected = { focus: vi.fn(), isConnected: true };
    const disconnected = { focus: vi.fn(), isConnected: false };
    const hidden = { focus: vi.fn(), getClientRects: () => [], isConnected: true };
    const fallback = { focus: vi.fn(), isConnected: true };
    const schedule = (callback: () => void) => callback();

    restoreModalTriggerFocus(connected, fallback, schedule);
    restoreModalTriggerFocus(disconnected, fallback, schedule);
    restoreModalTriggerFocus(hidden, fallback, schedule);

    expect(connected.focus).toHaveBeenCalledOnce();
    expect(disconnected.focus).not.toHaveBeenCalled();
    expect(hidden.focus).not.toHaveBeenCalled();
    expect(fallback.focus).toHaveBeenCalledTimes(2);
  });
});

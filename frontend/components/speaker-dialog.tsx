"use client";

import { FormEvent, useEffect, useRef } from "react";

import { activateModalDialog, handleModalCancel } from "@/lib/modal-dialog";
import { useI18n } from "@/lib/i18n/provider";

export function SpeakerDialog({
  error,
  onClose,
  onNameChange,
  onSubmit,
  saving,
  speakerName,
}: {
  error: string | null;
  onClose: () => void;
  onNameChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  saving: boolean;
  speakerName: string;
}) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    const input = nameInputRef.current;
    if (!dialog || !input) return;
    return activateModalDialog(dialog, input);
  }, []);

  return (
    <dialog
      aria-describedby="speaker-dialog-description"
      aria-labelledby="speaker-dialog-title"
      aria-modal="true"
      className="speakerDialog"
      onCancel={(event) => handleModalCancel(event, onClose)}
      ref={dialogRef}
      role="dialog"
    >
      <form onSubmit={onSubmit}>
        <span className="panelLabel">{t("speaker.eyebrow")}</span>
        <h2 id="speaker-dialog-title">{t("speaker.title")}</h2>
        <p id="speaker-dialog-description">{t("speaker.description")}</p>
        <label className="field" htmlFor="speaker-display-name">
          <span>{t("speaker.displayName")}</span>
          <input
            autoFocus
            id="speaker-display-name"
            onChange={(event) => onNameChange(event.target.value)}
            ref={nameInputRef}
            value={speakerName}
          />
        </label>
        {error ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
        <div className="dialogActions">
          <button className="secondaryButton" onClick={onClose} type="button">
            {t("speaker.cancel")}
          </button>
          <button className="primaryButton" disabled={saving || !speakerName.trim()} type="submit">
            {saving ? t("speaker.saving") : t("speaker.save")}
          </button>
        </div>
      </form>
    </dialog>
  );
}

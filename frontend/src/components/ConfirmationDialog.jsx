import { Modal } from "./Modal";
import { Button } from "./Button";

export function ConfirmationDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
  children,
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={busy ? undefined : onCancel}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Working…" : confirmLabel}
          </Button>
        </>
      }
    >
      {description ? <p>{description}</p> : null}
      {children}
    </Modal>
  );
}

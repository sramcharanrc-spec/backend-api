type DeleteClaimModalProps = {
  deleteTarget: any | null;
  deletingClaim: string | null;
  onCancel: () => void;
  onConfirm: () => void;
};

const DeleteClaimModal = ({
  deleteTarget,
  deletingClaim,
  onCancel,
  onConfirm,
}: DeleteClaimModalProps) => {
  if (!deleteTarget) return null;

  const claimId = deleteTarget.claim_id || deleteTarget.claimId || "this claim";

  return (
    <div className="cw-modal-backdrop">
      <div className="cw-modal cw-delete-modal">
        <div className="cw-modal-head">
          <h3>Delete Claim</h3>
        </div>

        <p>
          Are you sure you want to delete <strong>{claimId}</strong>? This action removes the
          claim from the workspace.
        </p>

        <div className="cw-modal-actions">
          <button type="button" className="cw-btn secondary" onClick={onCancel}>
            Cancel
          </button>

          <button
            type="button"
            className="cw-btn danger"
            onClick={onConfirm}
            disabled={Boolean(deletingClaim)}
          >
            {deletingClaim ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeleteClaimModal;
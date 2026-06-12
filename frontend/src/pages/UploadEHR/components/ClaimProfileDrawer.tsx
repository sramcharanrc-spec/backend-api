import { X } from "lucide-react";

type ClaimProfileDrawerProps = {
  profileOpen: string | null;
  profileData: any;
  onClose: () => void;
};

const ClaimProfileDrawer = ({
  profileOpen,
  profileData,
  onClose,
}: ClaimProfileDrawerProps) => {
  if (!profileOpen) return null;

  const claim = profileData?.claim?.claim || profileData?.claim?.payload?.claim || profileData?.claim || {};
  const pipeline = profileData?.pipeline || {};

  return (
    <div className="cw-profile-drawer">
      <div className="cw-profile-head">
        <div>
          <h3>Claim Profile</h3>
          <span>{profileOpen}</span>
        </div>

        <button type="button" onClick={onClose}>
          <X size={16} />
        </button>
      </div>

      {!profileData && <p>Loading profile...</p>}

      {profileData && (
        <div className="cw-profile-body">
          <section className="cw-panel">
            <h4>Claim</h4>

            <div className="cw-info-grid">
              <div className="cw-info-field">
                <span>Claim ID</span>
                <strong>{claim.claim_id || profileOpen}</strong>
              </div>

              <div className="cw-info-field">
                <span>Status</span>
                <strong>{claim.status || claim.pipeline_state || "Not reported"}</strong>
              </div>

              <div className="cw-info-field">
                <span>Patient</span>
                <strong>{claim.patient?.name || claim.patient_name || "Not reported"}</strong>
              </div>

              <div className="cw-info-field">
                <span>Payer</span>
                <strong>{claim.payer?.name || claim.payer || "Not reported"}</strong>
              </div>
            </div>
          </section>

          <section className="cw-panel">
            <h4>Pipeline</h4>

            <div className="cw-info-grid">
              <div className="cw-info-field">
                <span>Overall Status</span>
                <strong>{pipeline.overall_status || "Not reported"}</strong>
              </div>

              <div className="cw-info-field">
                <span>Current Agent</span>
                <strong>{pipeline.current_agent || "Not reported"}</strong>
              </div>

              <div className="cw-info-field">
                <span>Current Stage</span>
                <strong>{pipeline.current_stage || "Not reported"}</strong>
              </div>

              <div className="cw-info-field">
                <span>Progress</span>
                <strong>{pipeline.progress ?? "Not reported"}</strong>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
};

export default ClaimProfileDrawer;
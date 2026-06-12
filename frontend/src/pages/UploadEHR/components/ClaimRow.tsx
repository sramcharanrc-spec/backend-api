import React, { useCallback, useMemo } from "react";
import {
  ChevronDown,
  ChevronRight,
  Eye,
  MoreVertical,
  Trash2,
} from "lucide-react";

type ClaimRowProps = {
  item: any;
  claimId: string;
  expanded: boolean;
  progress: number | null;
  statusClassName: string;
  displayStatusText: string;
  mode: string;
  reviewStatus: string;
  queueState: string;
  currentStep: string;
  riskClassName: string;
  riskLabel: string;
  isNewClaim: boolean;
  isHighlighted: boolean;
  rowStateClass: string;
  activeTab: string;
  routingLabel: string;
  source: string;
  patientName: string;
  patientDob: string;
  payer: string;
  memberId: string;
  dos: string;
  amount: string;
  deleting: boolean;
  onView: (claimId: string) => void;
  onProfile: (claimId: string) => void;
  onDelete: (item: any) => void;
  setRowRef: (claimId: string, node: HTMLTableRowElement | null) => void;
};

const normalizeClassToken = (value: string) =>
  String(value || "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "-");

const ClaimRow: React.FC<ClaimRowProps> = ({
  item,
  claimId,
  expanded,
  progress,
  statusClassName,
  displayStatusText,
  mode,
  reviewStatus,
  queueState,
  currentStep,
  riskClassName,
  riskLabel,
  isNewClaim,
  isHighlighted,
  rowStateClass,
  activeTab,
  routingLabel,
  source,
  patientName,
  patientDob,
  payer,
  memberId,
  dos,
  amount,
  deleting,
  onView,
  onProfile,
  onDelete,
  setRowRef,
}) => {
  const progressValue = useMemo(() => {
    if (progress === null || progress === undefined || Number.isNaN(progress)) {
      return null;
    }

    return Math.min(100, Math.max(0, Math.round(progress)));
  }, [progress]);

  const rowClassName = useMemo(
    () =>
      [
        expanded ? "expanded-parent" : "",
        isHighlighted ? "cw-new-claim-row" : "",
        isNewClaim ? "cw-new-badge-row" : "",
        rowStateClass,
      ]
        .filter(Boolean)
        .join(" "),
    [expanded, isHighlighted, isNewClaim, rowStateClass]
  );

  const modeClassName = useMemo(
    () => `cw-mode-chip ${normalizeClassToken(mode)}`,
    [mode]
  );

  const reviewClassName = useMemo(
    () => `cw-review-badge ${normalizeClassToken(reviewStatus)}`,
    [reviewStatus]
  );

  const handleView = useCallback(() => {
    onView(claimId);
  }, [claimId, onView]);

  const handleProfile = useCallback(() => {
    onProfile(claimId);
  }, [claimId, onProfile]);

  const handleDelete = useCallback(() => {
    onDelete(item || { claim_id: claimId });
  }, [claimId, item, onDelete]);

  const handleRowRef = useCallback(
    (node: HTMLTableRowElement | null) => {
      setRowRef(claimId, node);
    },
    [claimId, setRowRef]
  );

  return (
    <tr ref={handleRowRef} className={rowClassName}>
      <td>
        <button className="cw-expand-btn" onClick={handleView}>
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
      </td>

      <td>
        <button className="cw-claim-link" onClick={handleView}>
          {claimId}
        </button>

        {isNewClaim && <span className="cw-new-badge">NEW</span>}

        {activeTab === "latest" && isNewClaim && (
          <span className="cw-routing-indicator">{routingLabel}</span>
        )}

        <span className="cw-source">{source}</span>
      </td>

      <td>
        <strong>{patientName}</strong>
        <span>{patientDob}</span>
      </td>

      <td>
        {payer}
        <span>{memberId}</span>
      </td>

      <td>{dos}</td>
      <td>{amount}</td>

      <td>
        <span className={statusClassName}>{displayStatusText}</span>
      </td>

      <td>
        <span className={modeClassName}>{mode}</span>
      </td>

      <td>
        <span className={reviewClassName}>{reviewStatus}</span>
      </td>

      <td>
        <span className="cw-step-chip">{queueState}</span>
      </td>

      <td>
        <span className="cw-step-chip">{currentStep}</span>
      </td>

      <td>
        <span className={`cw-risk ${riskClassName}`}>{riskLabel}</span>
      </td>

      <td>
        <div className="cw-progress-wrap">
          <strong>{progressValue === null ? "-" : `${progressValue}%`}</strong>
          <div className="cw-progress">
            <i style={{ width: `${progressValue ?? 0}%` }} />
          </div>
        </div>
      </td>

      <td>
        <div className="cw-row-actions">
          <button onClick={handleView} title="Review claim">
            <Eye size={16} />
          </button>

          <button onClick={handleProfile} title="Claim profile">
            <MoreVertical size={16} />
          </button>

          <button
            className="danger"
            disabled={deleting}
            onClick={handleDelete}
            title="Delete claim"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </td>
    </tr>
  );
};

export default React.memo(ClaimRow, (prev, next) => {
  return (
    prev.item === next.item &&
    prev.claimId === next.claimId &&
    prev.expanded === next.expanded &&
    prev.progress === next.progress &&
    prev.statusClassName === next.statusClassName &&
    prev.displayStatusText === next.displayStatusText &&
    prev.mode === next.mode &&
    prev.reviewStatus === next.reviewStatus &&
    prev.queueState === next.queueState &&
    prev.currentStep === next.currentStep &&
    prev.riskClassName === next.riskClassName &&
    prev.riskLabel === next.riskLabel &&
    prev.isNewClaim === next.isNewClaim &&
    prev.isHighlighted === next.isHighlighted &&
    prev.rowStateClass === next.rowStateClass &&
    prev.activeTab === next.activeTab &&
    prev.routingLabel === next.routingLabel &&
    prev.source === next.source &&
    prev.patientName === next.patientName &&
    prev.patientDob === next.patientDob &&
    prev.payer === next.payer &&
    prev.memberId === next.memberId &&
    prev.dos === next.dos &&
    prev.amount === next.amount &&
    prev.deleting === next.deleting &&
    prev.onView === next.onView &&
    prev.onProfile === next.onProfile &&
    prev.onDelete === next.onDelete &&
    prev.setRowRef === next.setRowRef
  );
});
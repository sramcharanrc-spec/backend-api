import ClaimRow from "./ClaimRow";

type ClaimTableProps = {
  items: any[];
  expandedRow: string | null;
  highlightedClaims?: Set<string>;
  setClaimRowRef?: (claimId: string, node: HTMLTableRowElement | null) => void;
  getClaimId: (item: any) => string;
  handleViewClaim: (claimId: string) => void;
  handleOpenProfile: (claimId: string) => void;
  handleDeleteRequest: (item: any) => void;
  handleAutoCorrect?: (item: any) => void;
  renderExpanded: (item: any) => React.ReactNode;
  handleSort?: (key: string) => void;
  SortIcon?: React.FC<{ col: string }>;
};

const ClaimTable = ({
  items,
  expandedRow,
  highlightedClaims = new Set(),
  setClaimRowRef,
  getClaimId,
  handleViewClaim,
  handleOpenProfile,
  handleDeleteRequest,
  handleAutoCorrect,
  renderExpanded,
  handleSort,
  SortIcon,
}: ClaimTableProps) => {
  return (
    <div className="cw-table-wrap">
      <table className="cw-table">
        <thead>
          <tr>
            <th onClick={() => handleSort?.("claim_id")}>
              Claim ID {SortIcon ? <SortIcon col="claim_id" /> : null}
            </th>
            <th onClick={() => handleSort?.("patient_name")}>
              Patient {SortIcon ? <SortIcon col="patient_name" /> : null}
            </th>
            <th onClick={() => handleSort?.("payer")}>
              Payer {SortIcon ? <SortIcon col="payer" /> : null}
            </th>
            <th onClick={() => handleSort?.("dos")}>
              DOS {SortIcon ? <SortIcon col="dos" /> : null}
            </th>
            <th onClick={() => handleSort?.("amount")}>
              Amount {SortIcon ? <SortIcon col="amount" /> : null}
            </th>
            <th>Status</th>
            <th>Agent</th>
            <th>Review</th>
            <th>Actions</th>
          </tr>
        </thead>

        <tbody>
          {items.length === 0 && (
            <tr>
              <td colSpan={9}>
                <div className="cw-empty-state">No claims found.</div>
              </td>
            </tr>
          )}

          {items.map((item) => {
            const claimId = getClaimId(item);
            const isExpanded = expandedRow === claimId;

            return (
              <ClaimRow
                key={claimId}
                item={item}
                claimId={claimId}
                isExpanded={isExpanded}
                isHighlighted={highlightedClaims.has(claimId)}
                setClaimRowRef={setClaimRowRef}
                onView={() => handleViewClaim(claimId)}
                onOpenProfile={() => handleOpenProfile(claimId)}
                onDelete={() => handleDeleteRequest(item)}
                onAutoCorrect={() => handleAutoCorrect?.(item)}
                expandedContent={isExpanded ? renderExpanded(item) : null}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default ClaimTable;
import { Filter, ListFilter, Search } from "lucide-react";

type ClaimFiltersProps = {
  search: string;
  setSearch: (value: string) => void;

  filter: string;
  setFilter: (value: string) => void;

  riskFilter: string;
  setRiskFilter: (value: string) => void;

  uploadTypeFilter: string;
  setUploadTypeFilter: (value: string) => void;

  payerFilter: string;
  setPayerFilter: (value: string) => void;

  agentFilter: string;
  setAgentFilter: (value: string) => void;

  dateFilter: string;
  setDateFilter: (value: string) => void;

  validationFilter: string;
  setValidationFilter: (value: string) => void;

  modeFilter: string;
  setModeFilter: (value: string) => void;

  reviewFilter: string;
  setReviewFilter: (value: string) => void;

  latestFilter: string;
  setLatestFilter: (value: string) => void;

  payerOptions: string[];
  agentOptions: string[];
  activeTab: string;
};

const ClaimFilters = ({
  search,
  setSearch,
  filter,
  setFilter,
  riskFilter,
  setRiskFilter,
  uploadTypeFilter,
  setUploadTypeFilter,
  payerFilter,
  setPayerFilter,
  agentFilter,
  setAgentFilter,
  dateFilter,
  setDateFilter,
  validationFilter,
  setValidationFilter,
  modeFilter,
  setModeFilter,
  reviewFilter,
  setReviewFilter,
  latestFilter,
  setLatestFilter,
  payerOptions,
  agentOptions,
  activeTab,
}: ClaimFiltersProps) => {
  return (
    <div className="cw-filters">
      <div className="cw-search">
        <Search size={16} />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search claim, patient, payer, agent..."
        />
      </div>

      {activeTab === "latest" && (
        <select value={latestFilter} onChange={(event) => setLatestFilter(event.target.value)}>
          <option value="ALL_RECENT">All recent</option>
          <option value="SINGLE_RECENT">Single uploads</option>
          <option value="BULK_RECENT">Bulk uploads</option>
          <option value="PROCESSING">Processing</option>
          <option value="WAITING_REVIEW">Waiting review</option>
          <option value="COMPLETED">Completed</option>
        </select>
      )}

      <select value={filter} onChange={(event) => setFilter(event.target.value)}>
        <option value="ALL">All statuses</option>
        <option value="PROCESSING">Processing</option>
        <option value="WAITING_FOR_REVIEW">Waiting Review</option>
        <option value="WAITING_FOR_APPROVAL">Waiting Approval</option>
        <option value="HITL_REQUIRED">HITL Required</option>
        <option value="FAILED">Failed</option>
        <option value="COMPLETED">Completed</option>
      </select>

      <select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}>
        <option value="ALL">All risks</option>
        <option value="LOW">Low</option>
        <option value="MEDIUM">Medium</option>
        <option value="HIGH">High</option>
      </select>

      <select value={uploadTypeFilter} onChange={(event) => setUploadTypeFilter(event.target.value)}>
        <option value="ALL">All uploads</option>
        <option value="SINGLE">Single</option>
        <option value="BULK">Bulk</option>
        <option value="PDF">PDF</option>
        <option value="IMAGE">Image</option>
      </select>

      <select value={payerFilter} onChange={(event) => setPayerFilter(event.target.value)}>
        <option value="ALL">All payers</option>
        {payerOptions.map((payer) => (
          <option key={payer} value={payer}>
            {payer}
          </option>
        ))}
      </select>

      <select value={agentFilter} onChange={(event) => setAgentFilter(event.target.value)}>
        <option value="ALL">All agents</option>
        {agentOptions.map((agent) => (
          <option key={agent} value={agent}>
            {agent}
          </option>
        ))}
      </select>

      <select value={dateFilter} onChange={(event) => setDateFilter(event.target.value)}>
        <option value="ALL">Any date</option>
        <option value="TODAY">Today</option>
        <option value="7D">Last 7 days</option>
        <option value="30D">Last 30 days</option>
      </select>

      <select value={validationFilter} onChange={(event) => setValidationFilter(event.target.value)}>
        <option value="ALL">Any validation</option>
        <option value="HIGH">High score</option>
        <option value="MEDIUM">Medium score</option>
        <option value="LOW">Low score</option>
      </select>

      <select value={modeFilter} onChange={(event) => setModeFilter(event.target.value)}>
        <option value="ALL">All modes</option>
        <option value="AUTO">Auto</option>
        <option value="MANUAL">Manual</option>
      </select>

      <select value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value)}>
        <option value="ALL">All reviews</option>
        <option value="PENDING">Pending</option>
        <option value="ACCEPTED">Accepted</option>
        <option value="REJECTED">Rejected</option>
        <option value="ESCALATED">Escalated</option>
        <option value="MANUAL_REQUIRED">Manual required</option>
      </select>

      <span className="cw-filter-icon">
        <Filter size={16} />
        <ListFilter size={16} />
      </span>
    </div>
  );
};

export default ClaimFilters;
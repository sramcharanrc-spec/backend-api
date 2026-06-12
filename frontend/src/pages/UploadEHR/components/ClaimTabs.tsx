import type { ClaimTab } from "../utils/claimTypes";

type ClaimTabsProps = {
  activeTab: ClaimTab;
  setActiveTab: (tab: ClaimTab) => void;
  tabCounts: Record<ClaimTab, number>;
};

const tabs: Array<{ key: ClaimTab; label: string }> = [
  { key: "latest", label: "Latest" },
  { key: "all", label: "All" },
  { key: "bulk", label: "Bulk" },
  { key: "single", label: "Single" },
  { key: "live", label: "Live" },
  { key: "review", label: "Review" },
  { key: "rejected", label: "Rejected" },
  { key: "completed", label: "Completed" },
];

const ClaimTabs = ({ activeTab, setActiveTab, tabCounts }: ClaimTabsProps) => {
  return (
    <div className="cw-tabs">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          className={`cw-tab ${activeTab === tab.key ? "active" : ""}`}
          onClick={() => setActiveTab(tab.key)}
        >
          <span>{tab.label}</span>
          <b>{tabCounts[tab.key] || 0}</b>
        </button>
      ))}
    </div>
  );
};

export default ClaimTabs;
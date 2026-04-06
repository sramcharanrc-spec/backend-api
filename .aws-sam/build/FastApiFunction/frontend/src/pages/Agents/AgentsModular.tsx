import React, { useState } from "react";
import AgentCard from "./components/AgentCard";
import AgentLogPanel from "./components/AgentLogPanel";
import AgentResultModal from "./components/AgentResultModal";
import { agentsList } from "./agents";
import useAgents from "./hooks/useAgents"; // default import

const AgentsModular: React.FC = () => {
  const { agents, logs, runAgent, runAllSequential, results } = useAgents(agentsList);

  const [modalOpen, setModalOpen] = useState(false);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);

  const handleView = (id: string) => {
    setActiveAgentId(id);
    setModalOpen(true);
  };

  const activeResult = activeAgentId ? results[activeAgentId] : undefined;

  return (
    <div className="p-6 space-y-6">
      {/* ... summary & agent grid ... */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {agents.map(a => (
          <AgentCard key={a.id} agent={a} onRun={runAgent} onView={handleView} />
        ))}
      </div>

      {/* AgentResultModal expects jobId, open and onClose (as per your component) */}
      <AgentResultModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        jobId={activeAgentId}
      />

      <AgentLogPanel logs={logs} />
    </div>
  );
};

export default AgentsModular;

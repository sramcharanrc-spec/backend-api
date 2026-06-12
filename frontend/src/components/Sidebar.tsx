import React from "react";
import logo from "/src/assets/ai-logo.png";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  FilePlus,
  BarChart3,
  Cpu,
  Settings,
  GitBranch as Workflow,
  Building,
  ShieldCheck,
  Activity,
} from "lucide-react";

interface NavItem {
  name: string;
  path: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
}

const Sidebar: React.FC = () => {
  const navItems: NavItem[] = [
    { name: "Command Center", path: "/dashboard", icon: LayoutDashboard },
    { name: "Claim Workspace", path: "/upload", icon: FilePlus },
    { name: "Clearinghouse",  path: "/clearinghouse", icon: Building },
    { name: "Case Management", path:"/case", icon: ShieldCheck },
    { name: "Analytics", path: "/analytics", icon: BarChart3 },
    { name: "AI Monitor", path: "/agents", icon: Cpu },
    { name: "RCM Process", path: "/end-to-end-rcm", icon: Workflow },
    { name: "Patients", path: "/patients", icon: Users },
    { name: "Settings", path: "/settings", icon: Settings },

  ];

  const base =
    "group relative flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300";

  return (
    <aside className="relative h-screen w-[280px] flex-shrink-0 overflow-hidden bg-[radial-gradient(circle_at_22%_4%,rgba(56,189,248,.32),transparent_26%),radial-gradient(circle_at_86%_18%,rgba(20,184,166,.22),transparent_24%),linear-gradient(180deg,#173b8f_0%,#0d1f52_45%,#08152f_100%)] text-white flex flex-col shadow-[22px_0_60px_rgba(8,21,47,.28)] border-r border-cyan-200/10">
      <div className="pointer-events-none absolute -left-20 top-24 h-48 w-48 rounded-full bg-cyan-300/15 blur-3xl" />
      <div className="pointer-events-none absolute -right-24 bottom-16 h-56 w-56 rounded-full bg-teal-300/12 blur-3xl" />
      
      {/* TOP LOGO HEADER */}
      <div className="relative p-6 border-b border-white/10 flex items-center gap-3">
      <div className="w-11 h-11 rounded-xl overflow-hidden shadow-inner ring-2 ring-cyan-300/30">
        <img 
        src={logo} 
       alt="Logo" 
        className="w-10 h-10 object-cover rounded-xl"
      />
      </div>

        <div>
          <h1 className="text-2xl font-bold tracking-wide">ProviderIQ</h1>
          <p className="text-cyan-100 text-sm -mt-1">AI Revenue Command</p>
        </div>
      </div>

      <div className="relative mx-5 mt-5 rounded-xl border border-cyan-300/20 bg-white/10 p-4 backdrop-blur-xl shadow-[0_18px_36px_rgba(8,21,47,.22)]">
        <div className="flex items-center gap-2 text-cyan-100 text-xs font-bold uppercase tracking-wide">
          <Activity size={14} /> Live Orchestration
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
          <i className="block h-full w-4/5 rounded-full bg-gradient-to-r from-emerald-400 via-cyan-300 to-blue-400" />
        </div>
        <p className="mt-2 text-xs text-slate-300">Claims, agents, HITL, clearinghouse</p>
      </div>

      {/* NAVIGATION */}
      <nav className="relative flex-1 p-5 space-y-2 overflow-y-auto">
        {navItems.map(({ name, path, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              isActive
                ? `${base} active bg-gradient-to-r from-white/95 to-cyan-100/90 text-slate-950 shadow-[0_14px_34px_rgba(56,189,248,.25)] ring-1 ring-cyan-200/40 translate-x-1`
                : `${base} text-cyan-50/85 hover:bg-white/12 hover:text-white hover:shadow-[0_12px_28px_rgba(14,165,233,.16)] hover:-translate-y-0.5`
            }
          >
            <span className="absolute left-0 top-1/2 h-7 w-1 -translate-y-1/2 rounded-r-full bg-cyan-300 opacity-0 transition-opacity duration-300 group-[.active]:opacity-100" />
            <Icon size={18} aria-hidden />
            <span className="font-medium">{name}</span>
          </NavLink>
        ))}
      </nav>

      {/* FOOTER VERSION TAG */}
      <div className="relative p-4 text-center text-sm text-cyan-100/80 border-t border-white/10">
        Enterprise AgenticAI v2.0
      </div>
    </aside>
  );
};

export default Sidebar;

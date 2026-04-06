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
  Wrench,
} from "lucide-react";

interface NavItem {
  name: string;
  path: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
}

const Sidebar: React.FC = () => {
  const navItems: NavItem[] = [
    { name: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { name: "EHR Upload", path: "/upload", icon: FilePlus },
    { name: "Patients", path: "/patients", icon: Users },
    { name: "Analytics", path: "/analytics", icon: BarChart3 },
    { name: "Agents", path: "/agents", icon: Cpu },
    { name: "Settings", path: "/settings", icon: Settings },
    { name: "RCM Process", path: "/end-to-end-rcm", icon: Workflow },
    { name: "RCM Dev Panel", path: "/rcm-dev", icon: Wrench },
  ];

  const base =
    "flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all duration-200";

  return (
    <aside className="w-64 bg-gradient-to-b from-blue-700 to-blue-900 text-white flex flex-col h-screen shadow-xl">
      
      {/* TOP LOGO HEADER */}
      <div className="p-6 border-b border-blue-800 flex items-center gap-3">
      <div className="w-10 h-10 rounded-xl overflow-hidden shadow-inner">
        <img 
  src={logo} 
  alt="Logo" 
  className="w-10 h-10 object-cover rounded-xl"
/>
      </div>

        <div>
          <h1 className="text-2xl font-bold tracking-wide">AgenticAI</h1>
          <p className="text-blue-200 text-sm -mt-1">Healthcare Ecosystem</p>
        </div>
      </div>

      {/* NAVIGATION */}
      <nav className="flex-1 p-8 space-y-2 overflow-y-auto">
        {navItems.map(({ name, path, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              isActive
                ? `${base} bg-blue-500 text-white shadow-md`
                : `${base} text-blue-100 hover:bg-blue-600/50 hover:text-white`
            }
          >
            <Icon size={18} aria-hidden />
            <span className="font-medium">{name}</span>
          </NavLink>
        ))}
      </nav>

      {/* FOOTER VERSION TAG */}
      <div className="p-4 text-center text-sm text-blue-200 border-t border-blue-800">
        AgenticAI v1.0
      </div>
    </aside>
  );
};

export default Sidebar;

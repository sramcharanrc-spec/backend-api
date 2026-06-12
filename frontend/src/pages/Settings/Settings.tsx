import React, { useState } from "react";
import {
  Settings,
  UserCog,
  Bell,
  ShieldCheck,
  Globe,
  Users,
  Plus,
  Edit,
  Trash,
} from "lucide-react";

const SettingsPage: React.FC = () => {
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [autoAssignAgents, setAutoAssignAgents] = useState(true);
  const [timezone, setTimezone] = useState("IST (UTC+5:30)");

  const users = [
    { email: "admin@test.com", role: "Admin", status: "Active" },
    { email: "doctor1@test.com", role: "Doctor", status: "Active" },
    { email: "coder@test.com", role: "Coder", status: "Suspended" },
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h2 className="page-title text-2xl font-bold text-blue-900 flex items-center gap-2">
          <Settings size={22} />
          System Settings
        </h2>
        <p className="text-sm text-gray-500">
          Manage organization preferences, system defaults, and user access.
        </p>
      </div>

      {/* Top Gradient Card */}
      <div className="rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-sky-500 p-5 text-white shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div>
            <p className="text-xs uppercase tracking-wide text-blue-100">
              Organization
            </p>
            <p className="text-2xl font-semibold">TestClinic</p>
            <p className="mt-1 text-xs text-blue-100">
              Settings apply to all users and AI agents in this workspace.
            </p>
          </div>

          <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[160px] text-sm">
            <div className="text-[11px] uppercase tracking-wide text-blue-100">
              Timezone
            </div>
            <div className="font-semibold">{timezone}</div>
          </div>
        </div>
      </div>

      {/* Settings Sections */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column */}
        <div className="space-y-6">
          {/* System Preferences */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                <UserCog size={18} />
                System Preferences
              </h3>
            </div>

            {/* Timezone */}
            <div className="space-y-1">
              <label className="text-xs text-gray-500">Timezone</label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full rounded-lg border-gray-300 shadow-sm text-sm"
              >
                <option>IST (UTC+5:30)</option>
                <option>PST (UTC−08:00)</option>
                <option>EST (UTC−05:00)</option>
                <option>CET (UTC+1:00)</option>
                <option>UTC (UTC 0)</option>
              </select>
            </div>

            {/* Auto Assign Agents */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-700">
                  Auto-Assign Agents
                </p>
                <p className="text-xs text-gray-500">
                  Automatically route tasks to AI agents.
                </p>
              </div>
              <label className="relative inline-flex cursor-pointer items-center">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={autoAssignAgents}
                  onChange={() => setAutoAssignAgents(!autoAssignAgents)}
                />
                <div className="peer h-5 w-10 rounded-full bg-gray-300 peer-checked:bg-blue-600 transition"></div>
                <div className="absolute left-1 top-0.5 h-4 w-4 rounded-full bg-white transition peer-checked:translate-x-5 shadow"></div>
              </label>
            </div>
          </div>

          {/* Notifications */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
            <h3 className="font-semibold text-gray-900 flex items-center gap-2">
              <Bell size={18} />
              Notifications
            </h3>

            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-700">Email Alerts</p>
                <p className="text-xs text-gray-500">
                  Alerts for claims, denials, and system updates.
                </p>
              </div>

              <label className="relative inline-flex cursor-pointer items-center">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={emailNotifications}
                  onChange={() => setEmailNotifications(!emailNotifications)}
                />
                <div className="peer h-5 w-10 rounded-full bg-gray-300 peer-checked:bg-blue-600 transition"></div>
                <div className="absolute left-1 top-0.5 h-4 w-4 rounded-full bg-white transition peer-checked:translate-x-5 shadow"></div>
              </label>
            </div>
          </div>
        </div>

        {/* Right Column: User Access Management */}
        <div className="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-900 flex items-center gap-2">
              <Users size={18} />
              User Access Management
            </h3>
            <button className="inline-flex items-center gap-1.5 rounded-full bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 text-xs shadow">
              <Plus size={14} /> Add User
            </button>
          </div>

          {/* User Table */}
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b">
                <th className="pb-2">User</th>
                <th className="pb-2">Role</th>
                <th className="pb-2">Status</th>
                <th className="pb-2"></th>
              </tr>
            </thead>
            <tbody>
              {[...users].map((u, idx) => (
                <tr
                  key={idx}
                  className="border-b hover:bg-gray-50 transition"
                >
                  <td className="py-2">{u.email}</td>
                  <td className="py-2">{u.role}</td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-1 rounded-full text-[11px] border ${
                        u.status === "Active"
                          ? "bg-emerald-50 text-emerald-700 border-emerald-100"
                          : "bg-rose-50 text-rose-700 border-rose-100"
                      }`}
                    >
                      {u.status}
                    </span>
                  </td>
                  <td className="py-2 flex items-center gap-3 text-gray-500">
                    <button className="hover:text-blue-600">
                      <Edit size={15} />
                    </button>
                    <button className="hover:text-red-600">
                      <Trash size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <button className="mt-4 w-full rounded-full border border-gray-200 bg-gray-50 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100 transition">
            View full audit logs
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;

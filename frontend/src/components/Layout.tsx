import React from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { Outlet } from "react-router-dom";

const Layout: React.FC = () => {
  return (
    <div className="enterprise-app-shell min-h-screen bg-slate-50 text-gray-900">
      {/* Sidebar */}
      <aside className="enterprise-sidebar-shell fixed left-0 top-0 z-30 h-screen w-[280px] flex-shrink-0">
        <Sidebar />
      </aside>

      {/* Main Content Area */}
      <div className="enterprise-main-shell ml-[280px] min-h-screen min-w-0 flex flex-col">
        {/* Header */}
        <header className="enterprise-header-shell sticky top-0 z-20">
          <Header />
        </header>

        {/* Page content from nested routes */}
        <main className="enterprise-page-shell flex-1 p-6">
          <div className="enterprise-page-frame mx-auto w-full max-w-[1800px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};

export default Layout;

import React, { useEffect, useState } from "react";
import { Bell, UserCircle2, Moon, Sun } from "lucide-react";
import { useNavigate } from "react-router-dom";

const Header: React.FC = () => {
  const [darkMode, setDarkMode] = useState(
    localStorage.getItem("theme") === "dark"
  );
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const navigate = useNavigate();

  // Dark mode toggle
  useEffect(() => {
    if (darkMode) {
      document.body.classList.add("dark");
      localStorage.setItem("theme", "dark");
    } else {
      document.body.classList.remove("dark");
      localStorage.setItem("theme", "light");
    }
  }, [darkMode]);

  // Logout with animation
  const handleLogout = () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);

    // wait for animation, then go to login
    setTimeout(() => {
      localStorage.removeItem("isLoggedIn");
      localStorage.removeItem("user");
      navigate("/login", { replace: true });
    }, 850);
  };

  return (
    <header className="h-16 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm flex items-center justify-between px-8 sticky top-0 z-20">
      <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 tracking-wide">
        AgenticAI Health
      </h2>

      <div className="flex items-center gap-5 text-gray-600 dark:text-gray-300">
        {/* Dark/Light Toggle */}
        <button
          onClick={() => setDarkMode(!darkMode)}
          aria-label="Toggle theme"
        >
          {darkMode ? <Sun size={20} /> : <Moon size={20} />}
        </button>

        {/* Notifications */}
        <button className="relative" aria-label="Notifications">
          <Bell size={20} />
          <span className="absolute top-0 right-0 w-2 h-2 bg-red-500 rounded-full"></span>
        </button>

        {/* User Info */}
        <div className="flex items-center gap-2">
          <UserCircle2 size={24} />
          <span className="font-medium">
            {JSON.parse(localStorage.getItem("user") || "{}").email ||
              "test@clinic.com"}
          </span>
        </div>

        {/* 🔥 Animated Logout Button */}
        <button
          onClick={handleLogout}
          disabled={isLoggingOut}
          className={[
            "logout-button",
            darkMode ? "logout-button--light" : "logout-button--dark",
            isLoggingOut ? "is-logging-out" : "",
          ].join(" ")}
        >
          <span className="logout-button__label">Logout</span>

          <span className="logout-button__icon">
            <span className="logout-button__person" />
            <span className="logout-button__door" />
          </span>
        </button>
      </div>
    </header>
  );
};

export default Header;

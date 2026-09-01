import React from 'react';

export function Header({
  activeTab,
  setActiveTab,
  darkMode,
  setDarkMode,
  mobileSidebarOpen,
  setMobileSidebarOpen,
  readyDocCount = 0,
}) {
  return (
    <header className="sticky top-0 z-30 bg-white/90 dark:bg-legal-900/90 backdrop-blur-md border-b border-legal-200 dark:border-legal-800 transition-colors duration-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Left: Mobile Toggle & Brand */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)}
              className="lg:hidden p-2 rounded-lg text-legal-600 dark:text-legal-300 hover:bg-legal-100 dark:hover:bg-legal-800 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              aria-label="Toggle Sidebar"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-linear-to-tr from-blue-700 to-indigo-600 flex items-center justify-center text-white shadow-md font-bold text-lg">
                ⚖️
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-lg text-legal-950 dark:text-white tracking-tight">
                    Nyaya
                  </span>
                  <span className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-full bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                    BNSS 2023
                  </span>
                </div>
                <p className="text-xs text-legal-500 dark:text-legal-400 hidden sm:block">
                  AI Legal Assistant & Statutory Forms
                </p>
              </div>
            </div>
          </div>

          {/* Center: Navigation Tabs */}
          <div className="flex items-center bg-legal-100 dark:bg-legal-800/80 p-1 rounded-xl border border-legal-200 dark:border-legal-700">
            <button
              type="button"
              onClick={() => setActiveTab('chat')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs md:text-sm font-medium transition-all ${
                activeTab === 'chat'
                  ? 'bg-white dark:bg-legal-900 text-blue-700 dark:text-blue-400 shadow-xs font-semibold'
                  : 'text-legal-600 dark:text-legal-400 hover:text-legal-900 dark:hover:text-white'
              }`}
            >
              <span>💬</span>
              <span>Chat Assistant</span>
              {readyDocCount > 0 && (
                <span className="w-2 h-2 rounded-full bg-purple-500" title="User document indexed" />
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('forms')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs md:text-sm font-medium transition-all ${
                activeTab === 'forms'
                  ? 'bg-white dark:bg-legal-900 text-blue-700 dark:text-blue-400 shadow-xs font-semibold'
                  : 'text-legal-600 dark:text-legal-400 hover:text-legal-900 dark:hover:text-white'
              }`}
            >
              <span>📑</span>
              <span>Statutory Forms (58)</span>
            </button>
          </div>

          {/* Right: Theme Toggle & Status */}
          <div className="flex items-center gap-3">
            {/* Dark Mode Toggle */}
            <button
              type="button"
              onClick={() => setDarkMode(!darkMode)}
              className="p-2 rounded-xl text-legal-600 dark:text-legal-300 hover:bg-legal-100 dark:hover:bg-legal-800 border border-legal-200 dark:border-legal-700 transition-colors cursor-pointer"
              title={darkMode ? "Switch to Light Mode" : "Switch to Dark Mode"}
              aria-label="Toggle Theme"
            >
              {darkMode ? (
                <svg className="w-5 h-5 text-amber-400" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"
                    clipRule="evenodd"
                  />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-legal-700" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Global Legal Disclaimer Strip */}
        <div className="py-1 px-2 text-center text-[11px] text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 border-t border-amber-200/60 dark:border-amber-900/40 font-medium">
          ⚖️ <span className="font-semibold">Informational Legal Aid:</span> Grounded strictly in BNSS 2023 & BNS offence schedules. Does not constitute formal legal counsel.
        </div>
      </div>
    </header>
  );
}

import React, { useState, useEffect } from 'react';

const API_BASE = typeof window !== 'undefined' && window.location.port === '5173'
  ? 'http://127.0.0.1:8000/api/v1'
  : '/api/v1';


export function FormsView() {
  const [forms, setForms] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedForm, setSelectedForm] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchForms();
  }, []);

  const fetchForms = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/forms`);
      if (!res.ok) throw new Error('Failed to fetch statutory forms');
      const data = await res.json();
      setForms(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredForms = forms.filter((f) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      f.title.toLowerCase().includes(q) ||
      (f.enabling_section && f.enabling_section.toLowerCase().includes(q)) ||
      `form ${f.form_number}`.includes(q) ||
      String(f.form_number) === q
    );
  });

  const handleDownloadAll = () => {
    window.location.href = `${API_BASE}/forms/download-all`;
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-legal-50/50 dark:bg-legal-950 overflow-hidden">
      {/* Forms Header Bar */}
      <div className="p-4 sm:p-6 bg-white dark:bg-legal-900 border-b border-legal-200 dark:border-legal-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-legal-950 dark:text-white tracking-tight">
              The Second Schedule — Statutory Forms
            </h2>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
              58 Vector Forms
            </span>
          </div>
          <p className="text-xs sm:text-sm text-legal-500 dark:text-legal-400 mt-1">
            Official procedural templates extracted directly from pages 190–249 of BNSS 2023.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleDownloadAll}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs sm:text-sm font-semibold shadow-sm transition-all cursor-pointer"
          >
            <span>📦</span>
            <span>Download All (58 ZIP)</span>
          </button>
        </div>
      </div>

      {/* Search & Filter Toolbar */}
      <div className="p-4 sm:px-6 bg-white/70 dark:bg-legal-900/70 border-b border-legal-200 dark:border-legal-800">
        <div className="max-w-xl relative">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-legal-400 pointer-events-none text-sm">
            🔍
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search forms by title, keyword (e.g. 'arrest', 'bail', 'charges'), or section number..."
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-legal-100 dark:bg-legal-800/80 border border-legal-200 dark:border-legal-700 text-xs sm:text-sm text-legal-900 dark:text-white placeholder-legal-400 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-legal-400 hover:text-legal-600 dark:hover:text-white text-xs"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Forms Grid Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {loading ? (
          <div className="text-center py-16 text-legal-500 dark:text-legal-400 text-sm">
            <span className="inline-block animate-spin mr-2">⏳</span>
            Loading 58 statutory form records...
          </div>
        ) : error ? (
          <div className="text-center py-16 text-red-500 text-sm">
            ⚠️ Error: {error}
          </div>
        ) : filteredForms.length === 0 ? (
          <div className="text-center py-16 text-legal-400 dark:text-legal-500 text-sm">
            No statutory forms matched "{searchQuery}".
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-7xl mx-auto">
            {filteredForms.map((form) => {
              const isMultiPage = form.page_start !== form.page_end;
              return (
                <div
                  key={form.id || form.form_number}
                  className="bg-white dark:bg-legal-900 rounded-2xl border border-legal-200 dark:border-legal-800 p-4 shadow-xs hover:shadow-md transition-all flex flex-col justify-between"
                >
                  <div>
                    {/* Card Top: Badges */}
                    <div className="flex items-center justify-between mb-2">
                      <span className="px-2 py-0.5 rounded-md bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300 font-bold text-xs border border-blue-200 dark:border-blue-800">
                        FORM No. {form.form_number}
                      </span>
                      <span className="text-[11px] text-legal-500 dark:text-legal-400 font-mono">
                        {isMultiPage ? `p.${form.page_start}-${form.page_end} (3 pages)` : `p.${form.page_start}`}
                      </span>
                    </div>

                    {/* Title */}
                    <h3 className="font-bold text-sm text-legal-950 dark:text-white line-clamp-2 mb-2 leading-snug">
                      {form.title}
                    </h3>

                    {/* Enabling Section */}
                    {form.enabling_section && (
                      <p className="text-xs text-legal-600 dark:text-legal-300 mb-3">
                        <span className="font-semibold text-legal-500 dark:text-legal-400">Enabling Sec: </span>
                        <span className="px-1.5 py-0.5 rounded bg-legal-100 dark:bg-legal-800 text-legal-800 dark:text-legal-200 font-mono text-[11px]">
                          {form.enabling_section}
                        </span>
                      </p>
                    )}
                  </div>

                  {/* Card Bottom Actions */}
                  <div className="flex items-center gap-2 pt-3 border-t border-legal-100 dark:border-legal-800">
                    <button
                      type="button"
                      onClick={() => setSelectedForm(form)}
                      className="flex-1 py-1.5 px-3 rounded-lg bg-legal-100 dark:bg-legal-800 hover:bg-legal-200 dark:hover:bg-legal-700 text-legal-800 dark:text-legal-200 text-xs font-semibold transition-colors text-center cursor-pointer"
                    >
                      👁️ Preview
                    </button>
                    <a
                      href={`${API_BASE}/forms/${form.form_number}/download`}
                      download={form.filename}
                      className="py-1.5 px-3 rounded-lg bg-blue-50 dark:bg-blue-950/60 hover:bg-blue-100 dark:hover:bg-blue-900/60 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 text-xs font-semibold transition-colors flex items-center gap-1 cursor-pointer"
                    >
                      <span>📥</span>
                      <span>PDF</span>
                    </a>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* PDF Viewer Modal */}
      {selectedForm && (
        <div className="fixed inset-0 z-50 overflow-hidden flex items-center justify-center p-4 sm:p-6">
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-xs transition-opacity"
            onClick={() => setSelectedForm(null)}
          />

          <div className="relative bg-white dark:bg-legal-900 rounded-2xl max-w-4xl w-full h-[85vh] shadow-2xl border border-legal-200 dark:border-legal-800 flex flex-col z-10 overflow-hidden">
            {/* Modal Header */}
            <div className="p-4 border-b border-legal-200 dark:border-legal-800 flex items-center justify-between bg-legal-50 dark:bg-legal-950">
              <div>
                <span className="text-xs font-bold text-blue-600 dark:text-blue-400">
                  FORM No. {selectedForm.form_number}
                </span>
                <h3 className="font-bold text-base text-legal-950 dark:text-white truncate max-w-xl">
                  {selectedForm.title}
                </h3>
              </div>

              <div className="flex items-center gap-2">
                <a
                  href={`${API_BASE}/forms/${selectedForm.form_number}/download`}
                  download={selectedForm.filename}
                  className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 transition-colors"
                >
                  📥 Download
                </a>
                <button
                  type="button"
                  onClick={() => setSelectedForm(null)}
                  className="p-1.5 rounded-lg text-legal-500 hover:bg-legal-200 dark:hover:bg-legal-800 transition-colors"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Modal PDF Frame */}
            <div className="flex-1 bg-legal-100 dark:bg-legal-950 p-2">
              <iframe
                src={`${API_BASE}/forms/${selectedForm.form_number}/download`}
                title={selectedForm.title}
                className="w-full h-full rounded-xl border border-legal-300 dark:border-legal-700 bg-white"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

import React from 'react';

export function SourceDrawer({ isOpen, onClose, sources, selectedCitation }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md md:max-w-lg bg-white dark:bg-legal-900 border-l border-legal-200 dark:border-legal-800 shadow-2xl flex flex-col">
          {/* Drawer Header */}
          <div className="p-4 border-b border-legal-200 dark:border-legal-800 flex items-center justify-between bg-legal-50 dark:bg-legal-950">
            <div className="flex items-center gap-2">
              <span className="text-xl">📜</span>
              <div>
                <h3 className="font-bold text-base text-legal-950 dark:text-white">
                  Statutory & Document Sources
                </h3>
                <p className="text-xs text-legal-500 dark:text-legal-400">
                  {sources?.length || 0} context chunk(s) verified in retrieval
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-legal-500 hover:bg-legal-200 dark:hover:bg-legal-800 transition-colors"
            >
              ✕
            </button>
          </div>

          {/* Drawer Content */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {selectedCitation && (
              <div className="p-2.5 rounded-xl bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-xs text-blue-900 dark:text-blue-200 flex items-center gap-2">
                <span>🎯</span>
                <span>
                  Filtering for citation: <strong className="font-semibold">{selectedCitation}</strong>
                </span>
              </div>
            )}

            {sources && sources.length > 0 ? (
              sources.map((src, idx) => {
                const isDoc = src.filename && !src.act;
                const isBns = src.act_short === 'BNS' || (src.act && src.act.includes('Nyaya'));

                return (
                  <div
                    key={src.chunk_id || idx}
                    className="p-4 rounded-xl bg-legal-50 dark:bg-legal-950/80 border border-legal-200 dark:border-legal-800 shadow-xs space-y-2"
                  >
                    {/* Header Badges */}
                    <div className="flex items-center justify-between flex-wrap gap-1.5">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`text-xs font-bold px-2 py-0.5 rounded-md border ${
                            isDoc
                              ? 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300 border-purple-200 dark:border-purple-800'
                              : isBns
                              ? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 border-amber-200 dark:border-amber-800'
                              : 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300 border-blue-200 dark:border-blue-800'
                          }`}
                        >
                          {isDoc ? 'User Case File' : isBns ? 'BNS 2023' : 'BNSS 2023'}
                        </span>

                        {src.section_number && (
                          <span className="text-xs font-bold text-legal-900 dark:text-legal-100">
                            Section {src.section_number}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5 text-[11px] text-legal-500 dark:text-legal-400">
                        {src.page_number && <span>Page {src.page_number}</span>}
                        {src.page_start && <span>p.{src.page_start}{src.page_end > src.page_start ? `-${src.page_end}` : ''}</span>}
                        {src.retrieval_method && (
                          <span className="px-1.5 py-0.5 rounded bg-legal-200 dark:bg-legal-800 text-[10px]">
                            {src.retrieval_method}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Section Title / Filename */}
                    {(src.section_title || src.filename) && (
                      <p className="text-xs font-semibold text-legal-800 dark:text-legal-200 italic">
                        {src.section_title || src.filename}
                      </p>
                    )}

                    {/* Text Body */}
                    <div className="text-xs text-legal-700 dark:text-legal-300 bg-white dark:bg-legal-900 p-3 rounded-lg border border-legal-200/80 dark:border-legal-800/80 font-mono leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
                      {src.text || src.section_title || '[Statutory section metadata retrieved via direct lookup]'}
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-center py-12 text-legal-400 dark:text-legal-500 text-sm">
                No context sources available for this response.
              </div>
            )}
          </div>

          {/* Drawer Footer */}
          <div className="p-3 border-t border-legal-200 dark:border-legal-800 bg-legal-50 dark:bg-legal-950 text-right">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-lg bg-legal-200 dark:bg-legal-800 text-legal-800 dark:text-legal-200 text-xs font-medium hover:bg-legal-300 dark:hover:bg-legal-700 transition-colors cursor-pointer"
            >
              Close Sources
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

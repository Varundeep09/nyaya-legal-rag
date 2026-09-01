import React, { useState, useRef } from 'react';

const API_BASE = 'http://127.0.0.1:8000/api/v1';

export function Sidebar({
  sessionId,
  setSessionId,
  conversations,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
  uploadedDocs,
  onFileUpload,
  mobileOpen,
  setMobileOpen,
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    setUploadError(null);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      processFile(files[0]);
    }
  };

  const handleFileSelect = (e) => {
    setUploadError(null);
    const files = e.target.files;
    if (files && files.length > 0) {
      processFile(files[0]);
    }
  };

  const processFile = (file) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Only PDF documents are supported.');
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setUploadError('File size exceeds 20MB limit.');
      return;
    }
    onFileUpload(file);
  };

  return (
    <>
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden backdrop-blur-xs transition-opacity"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={`fixed lg:static inset-y-0 left-0 z-40 w-72 sm:w-80 bg-legal-50 dark:bg-legal-950 border-r border-legal-200 dark:border-legal-800 flex flex-col transition-transform duration-300 ease-in-out ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Top: New Consultation Button */}
        <div className="p-4 border-b border-legal-200 dark:border-legal-800">
          <button
            type="button"
            onClick={() => {
              onNewChat();
              setMobileOpen(false);
            }}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 active:scale-[0.98] text-white font-medium text-sm shadow-sm transition-all cursor-pointer"
          >
            <span className="text-lg leading-none">+</span>
            <span>New Consultation</span>
          </button>
        </div>

        {/* Middle: Document Upload Area (2nd Corpus) */}
        <div className="p-4 border-b border-legal-200 dark:border-legal-800">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-legal-500 dark:text-legal-400">
              Session Case Files
            </span>
            <span className="text-[10px] text-purple-600 dark:text-purple-400 font-semibold bg-purple-100 dark:bg-purple-950/70 px-1.5 py-0.5 rounded border border-purple-200 dark:border-purple-800">
              Isolated
            </span>
          </div>

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleFileDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-3 text-center cursor-pointer transition-all ${
              isDragging
                ? 'border-blue-500 bg-blue-50/50 dark:bg-blue-950/40'
                : 'border-legal-300 dark:border-legal-700 hover:border-blue-400 dark:hover:border-blue-500 bg-white dark:bg-legal-900/60'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={handleFileSelect}
            />
            <div className="text-xl mb-1">📄</div>
            <p className="text-xs font-semibold text-legal-800 dark:text-legal-200">
              Upload FIR / Notice / Order
            </p>
            <p className="text-[11px] text-legal-500 dark:text-legal-400 mt-0.5">
              Drag & drop or click (PDF &lt; 20MB)
            </p>
          </div>

          {uploadError && (
            <p className="text-xs text-red-600 dark:text-red-400 mt-2 bg-red-50 dark:bg-red-950/50 p-2 rounded-lg border border-red-200 dark:border-red-800">
              ⚠️ {uploadError}
            </p>
          )}

          {/* Uploaded Documents List with Progress */}
          {uploadedDocs && uploadedDocs.length > 0 && (
            <div className="mt-3 space-y-2 max-h-36 overflow-y-auto pr-1">
              {uploadedDocs.map((doc) => {
                const isReady = doc.status === 'ready';
                const isFailed = doc.status === 'failed';
                const stagePercent = {
                  uploaded: 20,
                  parsing: 40,
                  chunking: 60,
                  embedding: 80,
                  ready: 100,
                  failed: 0,
                }[doc.status] || 30;

                return (
                  <div
                    key={doc.id || doc.filename}
                    className="p-2 rounded-lg bg-white dark:bg-legal-900 border border-legal-200 dark:border-legal-700/80 text-xs shadow-2xs"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-legal-800 dark:text-legal-200 truncate max-w-[170px]" title={doc.filename}>
                        {doc.filename}
                      </span>
                      <span
                        className={`text-[10px] font-semibold px-1.5 py-0.2 rounded ${
                          isReady
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                            : isFailed
                            ? 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300'
                            : 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 animate-pulse'
                        }`}
                      >
                        {doc.status}
                      </span>
                    </div>

                    {!isReady && !isFailed && (
                      <div className="w-full bg-legal-100 dark:bg-legal-800 h-1.5 rounded-full overflow-hidden mt-1.5">
                        <div
                          className="bg-blue-600 h-full transition-all duration-300"
                          style={{ width: `${stagePercent}%` }}
                        />
                      </div>
                    )}

                    {doc.error_message && (
                      <p className="text-[10px] text-red-500 mt-1">{doc.error_message}</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Bottom: Conversations History List */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="p-3 pb-1">
            <span className="text-xs font-bold uppercase tracking-wider text-legal-500 dark:text-legal-400">
              Consultation History
            </span>
          </div>

          <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-1">
            {conversations && conversations.length > 0 ? (
              conversations.map((convo) => {
                const isActive = convo.session_id === sessionId;
                return (
                  <div
                    key={convo.session_id}
                    onClick={() => {
                      onSelectConversation(convo.session_id);
                      setMobileOpen(false);
                    }}
                    className={`group flex items-center justify-between p-2.5 rounded-xl text-xs cursor-pointer transition-all ${
                      isActive
                        ? 'bg-blue-100/80 dark:bg-blue-950/70 text-blue-900 dark:text-blue-200 font-semibold border border-blue-200 dark:border-blue-800 shadow-2xs'
                        : 'hover:bg-legal-100 dark:hover:bg-legal-900 text-legal-700 dark:text-legal-300'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate pr-2">
                      <span className="text-sm">💬</span>
                      <span className="truncate">{convo.last_message || 'New Consultation'}</span>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteConversation(convo.session_id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 text-legal-400 hover:text-red-600 transition-opacity rounded"
                      title="Delete conversation"
                    >
                      🗑️
                    </button>
                  </div>
                );
              })
            ) : (
              <div className="text-center py-6 text-legal-400 dark:text-legal-500 text-xs">
                No past consultations yet
              </div>
            )}
          </div>
        </div>

        {/* Footer: System Status */}
        <div className="p-3 border-t border-legal-200 dark:border-legal-800 bg-white/50 dark:bg-legal-900/40 text-[11px] text-legal-500 dark:text-legal-400 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Hybrid Index Active</span>
          </div>
          <span>v1.0.0</span>
        </div>
      </aside>
    </>
  );
}

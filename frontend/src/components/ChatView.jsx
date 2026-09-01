import React, { useState, useRef, useEffect } from 'react';
import { FormattedMarkdown } from '../utils/markdown';

const EXAMPLE_PROMPTS = [
  {
    title: 'Section 103 BNSS',
    query: 'What is section 103 BNSS?',
    tag: 'Search & Witnesses',
  },
  {
    title: 'Arrest Without Warrant',
    query: 'Can a police officer arrest me without a warrant under BNSS?',
    tag: 'Section 35 Procedure',
  },
  {
    title: 'Rape Offence Classification',
    query: 'What is the punishment and bailable status for rape under BNS section 65(1)?',
    tag: 'BNS First Schedule',
  },
  {
    title: 'Bail in Non-Bailable Offences',
    query: 'When can bail be granted to an accused in a non-bailable offence under Section 480 of BNSS?',
    tag: 'Bail & Bonds',
  },
];

export function ChatView({
  messages,
  isStreaming,
  onSendMessage,
  onStopGeneration,
  onOpenSources,
  onCitationClick,
}) {
  const [inputMessage, setInputMessage] = useState('');
  const [copiedIdx, setCopiedIdx] = useState(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    if (!inputMessage.trim() || isStreaming) return;
    onSendMessage(inputMessage);
    setInputMessage('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleTextareaChange = (e) => {
    setInputMessage(e.target.value);
    // Auto-expand textarea
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
  };

  const copyToClipboard = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-white dark:bg-legal-900 overflow-hidden relative">
      {/* Scrollable Message History Area */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {messages.length === 0 ? (
          /* Empty State */
          <div className="max-w-2xl mx-auto my-auto text-center py-8">
            <div className="w-16 h-16 rounded-2xl bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 flex items-center justify-center text-3xl mx-auto mb-4 shadow-sm">
              ⚖️
            </div>
            <h2 className="text-xl sm:text-2xl font-bold text-legal-950 dark:text-white tracking-tight">
              Nyaya Legal Intelligence Engine
            </h2>
            <p className="mt-2 text-sm text-legal-600 dark:text-legal-400 leading-relaxed max-w-lg mx-auto">
              Ask statutory questions across <span className="font-semibold text-legal-800 dark:text-legal-200">BNSS 2023</span>, substantive offences in <span className="font-semibold text-legal-800 dark:text-legal-200">BNS 2023</span>, or upload case files for isolated document retrieval.
            </p>

            {/* Example Prompt Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-8 text-left">
              {EXAMPLE_PROMPTS.map((ex, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onSendMessage(ex.query)}
                  className="p-3.5 rounded-xl border border-legal-200 dark:border-legal-800 bg-legal-50/70 dark:bg-legal-950/50 hover:bg-blue-50/80 dark:hover:bg-blue-950/50 hover:border-blue-300 dark:hover:border-blue-700 transition-all text-left group cursor-pointer shadow-2xs"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-xs text-blue-700 dark:text-blue-400 group-hover:underline">
                      {ex.title}
                    </span>
                    <span className="text-[10px] text-legal-500 dark:text-legal-400 bg-legal-200/60 dark:bg-legal-800 px-1.5 py-0.5 rounded">
                      {ex.tag}
                    </span>
                  </div>
                  <p className="text-xs text-legal-700 dark:text-legal-300 line-clamp-2">
                    "{ex.query}"
                  </p>
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Message List */
          messages.map((msg, idx) => {
            const isUser = msg.role === 'user';
            return (
              <div
                key={msg.id || idx}
                className={`flex gap-3 max-w-4xl mx-auto ${
                  isUser ? 'justify-end' : 'justify-start'
                }`}
              >
                {!isUser && (
                  <div className="w-8 h-8 rounded-xl bg-blue-700 text-white flex items-center justify-center text-sm shrink-0 shadow-xs mt-1">
                    ⚖️
                  </div>
                )}

                <div
                  className={`relative rounded-2xl px-4 py-3 max-w-[88%] sm:max-w-[80%] ${
                    isUser
                      ? 'bg-blue-600 text-white rounded-br-xs shadow-sm'
                      : 'bg-legal-50 dark:bg-legal-950/80 border border-legal-200/80 dark:border-legal-800 text-legal-900 dark:text-legal-100 rounded-bl-xs shadow-xs'
                  }`}
                >
                  {isUser ? (
                    <p className="text-sm sm:text-base whitespace-pre-wrap leading-relaxed">
                      {msg.content}
                    </p>
                  ) : (
                    <div>
                      {/* Formatted Markdown with Interactive Citation Chips */}
                      <FormattedMarkdown
                        content={msg.content}
                        onCitationClick={onCitationClick}
                      />

                      {/* Citation Guard Alert (if any hallucinated citations were stripped) */}
                      {msg.stripped_hallucinations && msg.stripped_hallucinations.length > 0 && (
                        <div className="mt-3 p-2 rounded-lg bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-300">
                          🛡️ <strong>Citation Guard:</strong> Stripped {msg.stripped_hallucinations.length} unverified citation(s) not found in retrieved statutory context.
                        </div>
                      )}

                      {/* Bottom Action Strip */}
                      <div className="flex items-center justify-between pt-3 mt-3 border-t border-legal-200/60 dark:border-legal-800/60 text-xs text-legal-500 dark:text-legal-400">
                        <div className="flex items-center gap-2">
                          {msg.sources && msg.sources.length > 0 && (
                            <button
                              type="button"
                              onClick={() => onOpenSources(msg.sources)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-legal-200/60 dark:bg-legal-800 text-legal-700 dark:text-legal-300 hover:bg-legal-300 dark:hover:bg-legal-700 transition-colors font-medium cursor-pointer"
                            >
                              <span>📚</span>
                              <span>{msg.sources.length} Context Sources</span>
                            </button>
                          )}
                        </div>

                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => copyToClipboard(msg.content, idx)}
                            className="p-1 rounded hover:bg-legal-200 dark:hover:bg-legal-800 transition-colors"
                            title="Copy response"
                          >
                            {copiedIdx === idx ? '✓ Copied' : '📋 Copy'}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {isUser && (
                  <div className="w-8 h-8 rounded-xl bg-legal-300 dark:bg-legal-700 text-legal-800 dark:text-white flex items-center justify-center text-xs font-bold shrink-0 mt-1">
                    👤
                  </div>
                )}
              </div>
            );
          })
        )}

        {isStreaming && (
          <div className="flex gap-3 max-w-4xl mx-auto justify-start">
            <div className="w-8 h-8 rounded-xl bg-blue-700 text-white flex items-center justify-center text-sm shrink-0 shadow-xs mt-1 animate-pulse">
              ⚖️
            </div>
            <div className="bg-legal-50 dark:bg-legal-950/80 border border-legal-200/80 dark:border-legal-800 rounded-2xl px-4 py-3 text-xs text-legal-500 dark:text-legal-400 flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-blue-600 animate-ping" />
              <span>Synthesizing verified statutory answer...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar Area */}
      <div className="p-4 border-t border-legal-200 dark:border-legal-800 bg-white dark:bg-legal-900">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto relative">
          <div className="flex items-end gap-2 bg-legal-50 dark:bg-legal-950 rounded-2xl border border-legal-300 dark:border-legal-700 p-2 shadow-sm focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-transparent transition-all">
            <textarea
              ref={textareaRef}
              value={inputMessage}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question on BNSS procedure, BNS offences, or your uploaded case files..."
              rows={1}
              className="flex-1 bg-transparent border-0 resize-none px-2 py-1.5 text-sm text-legal-900 dark:text-white placeholder-legal-400 dark:placeholder-legal-500 focus:outline-hidden max-h-44"
            />

            {isStreaming ? (
              <button
                type="button"
                onClick={onStopGeneration}
                className="px-3.5 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-semibold shadow-sm transition-all flex items-center gap-1 cursor-pointer"
              >
                <span>⏹</span>
                <span>Stop</span>
              </button>
            ) : (
              <button
                type="submit"
                disabled={!inputMessage.trim()}
                className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold shadow-sm transition-all flex items-center gap-1 cursor-pointer"
              >
                <span>Send</span>
                <span>➔</span>
              </button>
            )}
          </div>
          <div className="flex items-center justify-between text-[11px] text-legal-400 dark:text-legal-500 mt-1.5 px-2">
            <span>Shift + Enter for new line • Enter to send</span>
            <span>Grounded in Indian Criminal Code 2023</span>
          </div>
        </form>
      </div>
    </div>
  );
}

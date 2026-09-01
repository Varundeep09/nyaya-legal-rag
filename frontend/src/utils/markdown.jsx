import React from 'react';

/**
 * Parses bracketed legal citations ([BNSS s.X], [BNS s.Y], [Doc: file, p.Z])
 * and returns React elements with clickable citation chips.
 */
export function renderTextWithCitations(text, onCitationClick) {
  if (!text) return null;

  // Regex to match statutory citations and document citations
  const citationRegex = /\[(BNSS\s+s\.[0-9a-zA-Z\(\)]+|BNS\s+s\.[0-9a-zA-Z\(\)]+|Doc:\s*[^\]]+)\]/g;
  
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = citationRegex.exec(text)) !== null) {
    // Text before match
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }

    const fullCitation = match[0]; // e.g. "[BNSS s.35(3)]"
    const citationBody = match[1]; // e.g. "BNSS s.35(3)" or "Doc: FIR.pdf, p.1"
    const isDoc = citationBody.startsWith('Doc:');
    const isBns = citationBody.startsWith('BNS ');

    parts.push(
      <button
        key={`cit-${match.index}`}
        type="button"
        onClick={() => onCitationClick && onCitationClick(citationBody)}
        className={`inline-flex items-center gap-1 mx-1 px-2 py-0.5 text-xs font-semibold rounded-md border transition-all cursor-pointer shadow-xs ${
          isDoc
            ? 'bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800'
            : isBns
            ? 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800'
            : 'bg-blue-50 text-blue-800 border-blue-200 hover:bg-blue-100 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800'
        }`}
        title={`Click to view statutory source context for ${citationBody}`}
      >
        <span>{isDoc ? '📄' : isBns ? '⚖️' : '📜'}</span>
        <span>{citationBody}</span>
      </button>
    );

    lastIndex = match.index + fullCitation.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts;
}

/**
 * Lightweight custom markdown formatter that handles headers, bold, bullet points,
 * numbered lists, paragraphs, and citations without heavy external dependencies.
 */
export function FormattedMarkdown({ content, onCitationClick }) {
  if (!content) return null;

  const lines = content.split('\n');
  const elements = [];
  let inList = false;
  let listItems = [];

  const flushList = () => {
    if (inList && listItems.length > 0) {
      elements.push(
        <ul key={`list-${elements.length}`} className="list-disc pl-5 my-2 space-y-1">
          {listItems.map((item, idx) => (
            <li key={idx} className="leading-relaxed">
              {renderTextWithCitations(item, onCitationClick)}
            </li>
          ))}
        </ul>
      );
      listItems = [];
      inList = false;
    }
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();

    if (!trimmed) {
      flushList();
      return;
    }

    // Headers
    if (trimmed.startsWith('### ')) {
      flushList();
      elements.push(
        <h3 key={idx} className="text-base font-bold mt-4 mb-1.5 text-legal-900 dark:text-legal-100">
          {renderTextWithCitations(trimmed.slice(4), onCitationClick)}
        </h3>
      );
    } else if (trimmed.startsWith('## ')) {
      flushList();
      elements.push(
        <h2 key={idx} className="text-lg font-bold mt-5 mb-2 text-legal-950 dark:text-white border-b border-legal-200 dark:border-legal-800 pb-1">
          {renderTextWithCitations(trimmed.slice(3), onCitationClick)}
        </h2>
      );
    } else if (trimmed.startsWith('# ')) {
      flushList();
      elements.push(
        <h1 key={idx} className="text-xl font-extrabold mt-6 mb-2 text-legal-950 dark:text-white">
          {renderTextWithCitations(trimmed.slice(2), onCitationClick)}
        </h1>
      );
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      // Unordered list item
      inList = true;
      listItems.push(trimmed.slice(2));
    } else if (/^\d+\.\s/.test(trimmed)) {
      // Numbered item
      inList = true;
      listItems.push(trimmed.replace(/^\d+\.\s/, ''));
    } else if (trimmed.startsWith('> ')) {
      // Blockquote
      flushList();
      elements.push(
        <blockquote
          key={idx}
          className="border-l-4 border-legal-400 dark:border-legal-600 pl-3 my-2 text-legal-600 dark:text-legal-300 italic"
        >
          {renderTextWithCitations(trimmed.slice(2), onCitationClick)}
        </blockquote>
      );
    } else {
      flushList();
      elements.push(
        <p key={idx} className="my-2 leading-relaxed text-legal-800 dark:text-legal-200">
          {renderTextWithCitations(trimmed, onCitationClick)}
        </p>
      );
    }
  });

  flushList();

  return <div className="space-y-1 text-sm md:text-base">{elements}</div>;
}

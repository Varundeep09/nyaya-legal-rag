import React, { useState, useEffect, useRef } from 'react';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { ChatView } from './components/ChatView';
import { FormsView } from './components/FormsView';
import { SourceDrawer } from './components/SourceDrawer';

const API_BASE = 'http://127.0.0.1:8000/api/v1';

function generateSessionId() {
  return 'sess_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now().toString(36);
}

export default function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [darkMode, setDarkMode] = useState(() => {
    return localStorage.getItem('nyaya_theme') === 'dark';
  });
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const [sessionId, setSessionId] = useState(() => {
    return localStorage.getItem('nyaya_active_session') || generateSessionId();
  });
  const [conversations, setConversations] = useState([]);
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const [sourceDrawerOpen, setSourceDrawerOpen] = useState(false);
  const [currentSources, setCurrentSources] = useState([]);
  const [selectedCitation, setSelectedCitation] = useState(null);

  const [uploadedDocs, setUploadedDocs] = useState([]);
  const abortControllerRef = useRef(null);

  // Sync dark mode class on <html> element
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('nyaya_theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('nyaya_theme', 'light');
    }
  }, [darkMode]);

  // Save active session
  useEffect(() => {
    localStorage.setItem('nyaya_active_session', sessionId);
  }, [sessionId]);

  // Load conversation list on mount
  useEffect(() => {
    fetchConversations();
  }, []);

  const fetchConversations = async () => {
    try {
      const res = await fetch(`${API_BASE}/conversations`);
      if (res.ok) {
        const data = await res.json();
        setConversations(data);
      }
    } catch (err) {
      console.warn('Failed to load conversations:', err);
    }
  };

  // Start new consultation
  const handleNewChat = () => {
    if (isStreaming) handleStopGeneration();
    const newId = generateSessionId();
    setSessionId(newId);
    setMessages([]);
    setCurrentSources([]);
    setSelectedCitation(null);
    setUploadedDocs([]);
  };

  // Select an existing conversation
  const handleSelectConversation = async (selectedId) => {
    if (isStreaming) handleStopGeneration();
    setSessionId(selectedId);
    try {
      const res = await fetch(`${API_BASE}/conversations/${selectedId}/messages`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data);
      }
    } catch (err) {
      console.error('Failed to fetch conversation history:', err);
    }
  };

  // Delete a conversation
  const handleDeleteConversation = async (idToDelete) => {
    try {
      await fetch(`${API_BASE}/conversations/${idToDelete}`, { method: 'DELETE' });
      setConversations((prev) => prev.filter((c) => c.session_id !== idToDelete));
      if (sessionId === idToDelete) {
        handleNewChat();
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  };

  // Upload a case file PDF & poll status
  const handleFileUpload = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    const tempDoc = {
      filename: file.name,
      status: 'uploading',
    };
    setUploadedDocs((prev) => [...prev, tempDoc]);

    try {
      const res = await fetch(`${API_BASE}/documents/upload`, {
        method: 'POST',
        headers: {
          'X-Session-ID': sessionId,
        },
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Upload failed');
      }

      const docInfo = await res.json();
      // Update with server ID
      setUploadedDocs((prev) =>
        prev.map((d) => (d.filename === file.name ? { ...d, id: docInfo.id, status: docInfo.status } : d))
      );

      // Poll document status
      pollDocumentStatus(docInfo.id, file.name);
    } catch (err) {
      setUploadedDocs((prev) =>
        prev.map((d) =>
          d.filename === file.name ? { ...d, status: 'failed', error_message: err.message } : d
        )
      );
    }
  };

  const pollDocumentStatus = (docId, filename) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/documents/${docId}/status`);
        if (res.ok) {
          const statusData = await res.json();
          setUploadedDocs((prev) =>
            prev.map((d) => (d.id === docId ? { ...d, status: statusData.status, error_message: statusData.error_message } : d))
          );

          if (statusData.status === 'ready' || statusData.status === 'failed') {
            clearInterval(interval);
          }
        }
      } catch (err) {
        console.warn('Status poll error:', err);
        clearInterval(interval);
      }
    }, 1500);
  };

  // Send message and stream response via SSE
  const handleSendMessage = async (text) => {
    if (!text.trim() || isStreaming) return;

    const userMessage = {
      id: 'msg_' + Date.now(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };

    const initialAssistantMessage = {
      id: 'msg_ast_' + Date.now(),
      role: 'assistant',
      content: '',
      sources: [],
      stripped_hallucinations: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage, initialAssistantMessage]);
    setIsStreaming(true);

    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': sessionId,
        },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let accumulatedText = '';
      let latestSources = [];
      let latestStripped = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data: ')) {
            const rawJson = trimmed.slice(6);
            try {
              const event = JSON.parse(rawJson);
              if (event.event === 'token') {
                accumulatedText += event.data;
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                    updated[lastIdx] = {
                      ...updated[lastIdx],
                      content: accumulatedText,
                    };
                  }
                  return updated;
                });
              } else if (event.event === 'sources') {
                latestSources = event.data;
                setCurrentSources(latestSources);
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                    updated[lastIdx] = {
                      ...updated[lastIdx],
                      sources: latestSources,
                    };
                  }
                  return updated;
                });
              } else if (event.event === 'guard_warning') {
                latestStripped = event.data?.hallucinated_citations || [];
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                    updated[lastIdx] = {
                      ...updated[lastIdx],
                      stripped_hallucinations: latestStripped,
                    };
                  }
                  return updated;
                });
              } else if (event.event === 'done') {
                fetchConversations();
              }
            } catch (jsonErr) {
              console.warn('SSE JSON parse error:', jsonErr, rawJson);
            }
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('Chat stream error:', err);
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
            updated[lastIdx] = {
              ...updated[lastIdx],
              content: updated[lastIdx].content + `\n\n⚠️ Error: ${err.message}`,
            };
          }
          return updated;
        });
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
    }
  };

  const handleOpenSources = (sources) => {
    setCurrentSources(sources || []);
    setSelectedCitation(null);
    setSourceDrawerOpen(true);
  };

  const handleCitationClick = (citationText) => {
    setSelectedCitation(citationText);
    setSourceDrawerOpen(true);
  };

  const readyDocs = uploadedDocs.filter((d) => d.status === 'ready');

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-white dark:bg-legal-950 font-sans text-legal-900 dark:text-legal-100 transition-colors duration-200">
      {/* Top Navbar */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        darkMode={darkMode}
        setDarkMode={setDarkMode}
        mobileSidebarOpen={mobileSidebarOpen}
        setMobileSidebarOpen={setMobileSidebarOpen}
        readyDocCount={readyDocs.length}
      />

      {/* Two-Panel Workspace */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left Sidebar (Only in Chat view or responsive overlay) */}
        {activeTab === 'chat' && (
          <Sidebar
            sessionId={sessionId}
            setSessionId={setSessionId}
            conversations={conversations}
            onNewChat={handleNewChat}
            onSelectConversation={handleSelectConversation}
            onDeleteConversation={handleDeleteConversation}
            uploadedDocs={uploadedDocs}
            onFileUpload={handleFileUpload}
            mobileOpen={mobileSidebarOpen}
            setMobileOpen={setMobileSidebarOpen}
          />
        )}

        {/* Main Panel Content */}
        <main className="flex-1 flex flex-col h-full overflow-hidden">
          {activeTab === 'chat' ? (
            <ChatView
              messages={messages}
              isStreaming={isStreaming}
              onSendMessage={handleSendMessage}
              onStopGeneration={handleStopGeneration}
              onOpenSources={handleOpenSources}
              onCitationClick={handleCitationClick}
            />
          ) : (
            <FormsView />
          )}
        </main>
      </div>

      {/* Source Drawer for Citations & Context */}
      <SourceDrawer
        isOpen={sourceDrawerOpen}
        onClose={() => setSourceDrawerOpen(false)}
        sources={currentSources}
        selectedCitation={selectedCitation}
      />
    </div>
  );
}

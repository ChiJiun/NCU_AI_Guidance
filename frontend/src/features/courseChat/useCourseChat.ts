import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { chatAPI, chatStreamAPI } from '../../api/services';
import { useAuth } from '../../auth/AuthContext';
import { useLiveAiAccess } from '../../hooks/useLiveAiAccess';
import { demoAPI, type CourseDemoCase, type DemoCategory } from '../../demo/demoCases';
import type { CourseCard, DebugTrace, StreamEvent, ToolTraceItem } from '../../types';

export interface ToolIndicator {
  name: string;
  done: boolean;
  count?: number;
}

export interface Message {
  role:         'user' | 'assistant';
  content:      string;
  timestamp:    Date;
  isStreaming?: boolean;
  courseCards?: CourseCard[];
  toolsUsed?:  string[];
  debugTrace?: DebugTrace;
}

export interface Conversation {
  id:        string;
  title:     string;
  messages:  Message[];
  createdAt: Date;
  updatedAt: Date;
  isStub?:   boolean; // true = metadata only, full turns not yet loaded
  /** 展示版的預先錄製對話 */
  demo?:     { category: DemoCategory; summary: string; field: string; reviewed: boolean; recordedAt: string };
}

export const GREETING = '你好，我是課程推薦助理。你可以直接問我課程方向、學分安排，或想比較的學院特色。';

export function makeConvFromSession(detail: {
  session_id: string;
  title: string;
  updated_at: string;
  turns: Array<{
    user: string; assistant: string;
    course_cards: CourseCard[];
    tools_used: string[]; created_at: string;
    debug_trace?: { toolCalls: ToolTraceItem[] };
  }>;
}): Conversation {
  const messages: Message[] = [
    { role: 'assistant', content: GREETING, timestamp: new Date() },
  ];
  for (const t of detail.turns) {
    const ts = new Date(t.created_at);
    messages.push({ role: 'user', content: t.user, timestamp: ts });
    const dt = t.debug_trace;
    const debugTrace: DebugTrace | undefined = dt?.toolCalls?.length
      ? { toolCalls: dt.toolCalls, verify: null }
      : undefined;
    messages.push({
      role: 'assistant', content: t.assistant, timestamp: ts,
      courseCards: t.course_cards ?? [],
      toolsUsed:   t.tools_used  ?? [],
      debugTrace,
    });
  }
  const updatedAt = new Date(detail.updated_at || Date.now());
  return {
    id: detail.session_id,
    title: detail.title || '未命名對話',
    messages,
    createdAt: updatedAt,
    updatedAt,
    isStub: false,
  };
}

/** 把一組預先錄製的示範轉成對話（展示版、不能即時提問時顯示）。 */
export function makeConvFromDemo(c: CourseDemoCase): Conversation {
  const ts = new Date(c.recorded_at);
  const messages: Message[] = [{ role: 'assistant', content: GREETING, timestamp: ts }];
  for (const t of c.turns) {
    messages.push({ role: 'user', content: t.user, timestamp: ts });
    messages.push({
      role: 'assistant', content: t.assistant, timestamp: ts,
      courseCards: t.course_cards ?? [],
      toolsUsed:   t.tools_used ?? [],
      debugTrace:  t.debug_trace?.toolCalls?.length
        ? { toolCalls: t.debug_trace.toolCalls, verify: t.debug_trace.verify ?? null }
        : undefined,
    });
  }
  return {
    id: c.id, title: c.title, messages, createdAt: ts, updatedAt: ts,
    demo: { category: c.category, summary: c.summary, field: c.field ?? '', reviewed: c.reviewed, recordedAt: c.recorded_at },
  };
}

function lastCourseCards(conv: Conversation): CourseCard[] {
  const last = [...conv.messages].reverse().find(
    (m) => m.role === 'assistant' && !m.isStreaming && (m.courseCards?.length ?? 0) > 0,
  );
  return last?.courseCards ?? [];
}

export function formatTime(date: Date): string {
  const diff = Date.now() - date.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return '今天';
  if (days === 1) return '昨天';
  if (days < 7) return `${days} 天前`;
  return date.toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' });
}

/**
 * 課程助理（AI 對話）的資料邏輯：歷史對話載入、對話管理、串流送出與中止、原地編輯、
 * 推薦課程面板，以及即時 AI 權限（LIVE_AI_RESTRICTED）處理。新舊版頁面共用這個 hook。
 */
export function useCourseChat({ demo = false }: { demo?: boolean } = {}) {
  const { user, loading: authLoading } = useAuth();
  const liveAi = useLiveAiAccess();
  // 已經載入這位使用者的真實對話：之後才被擋（對話端點回 403）時保留原本的對話，不換成示範
  const [realLoadedFor, setRealLoadedFor] = useState<string | null>(null);
  // 展示版：後端明確不開放即時 AI 時，改看預先錄製的示範對話（只有傳入 demo 的頁面才會顯示）
  const showDemo = demo && liveAi.status === 'restricted' && !(user && realLoadedFor === user.id);
  const [conversations, setConversations]       = useState<Conversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState('');
  const [inputMessage, setInputMessage]         = useState('');
  const [isMobileConversationOpen, setIsMobileConversationOpen] = useState(false);
  const [sessionsLoaded, setSessionsLoaded]     = useState(false);

  // 串流狀態
  const [isStreaming, setIsStreaming]   = useState(false);
  const [activeTools, setActiveTools]   = useState<ToolIndicator[]>([]);
  const [isVerifying, setIsVerifying]   = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const activeTraceRef = useRef<{ toolCalls: ToolTraceItem[]; poolSize: number }>({ toolCalls: [], poolSize: 0 });

  // 原地編輯狀態
  const [editingMsgIdx, setEditingMsgIdx]       = useState(-1);
  const [editingContent, setEditingContent]     = useState('');

  // 右側推薦課程
  const [panelCourses, setPanelCourses] = useState<CourseCard[]>([]);

  const sessionIds    = useRef<Record<string, string>>({});

  const selectedConversation = useMemo(
    () => conversations.find((c) => c.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );

  const demoListItems = useMemo(
    () => conversations.flatMap((c) => c.demo ? [{
      id: c.id, title: c.title, category: c.demo.category, summary: c.demo.summary, reviewed: c.demo.reviewed,
      meta: [c.demo.field, `${c.messages.filter((m) => m.role === 'user').length} 輪`].filter(Boolean).join('｜'),
    }] : []),
    [conversations],
  );
  const demoQuestions = useMemo(
    () => conversations.flatMap((c) => {
      const q = c.demo ? c.messages.find((m) => m.role === 'user')?.content : undefined;
      return q ? [{ id: c.id, question: q }] : [];
    }),
    [conversations],
  );

  const createDefaultConversation = useCallback(() => {
    const nc: Conversation = {
      id: Date.now().toString(), title: '新對話',
      messages: [{ role: 'assistant', content: GREETING, timestamp: new Date() }],
      createdAt: new Date(), updatedAt: new Date(),
    };
    setConversations([nc]);
    setSelectedConversationId(nc.id);
  }, []);

  // ── 載入歷史對話（先拿 metadata，選到才 fetch 詳情）─────────────────────
  useEffect(() => {
    if (authLoading || liveAi.loading) return;
    let cancelled = false;

    void (async () => {
      await Promise.resolve();
      if (showDemo) {
        setSessionsLoaded(false);
        sessionIds.current = {};
        const cases = await demoAPI.courseCases();
        if (cancelled) return;
        const convs = cases.map(makeConvFromDemo);
        if (convs.length === 0) {
          createDefaultConversation();
        } else {
          // 首頁可以用 ?demo=<id> 直接開某一組示範
          const wanted = new URLSearchParams(window.location.search).get('demo');
          const first = convs.find((c) => c.id === wanted) ?? convs[0];
          setConversations(convs);
          setSelectedConversationId(first.id);
          setPanelCourses(lastCourseCards(first));
        }
        setSessionsLoaded(true);
        return;
      }
      if (!user) {
        createDefaultConversation();
        setSessionsLoaded(true);
        return;
      }

      setSessionsLoaded(false);
      sessionIds.current = {};
      setPanelCourses([]);

      try {
        const sessions = await chatAPI.getSessions();
        if (cancelled) return;
        setRealLoadedFor(user.id);
        if (sessions.length === 0) {
          createDefaultConversation();
          setSessionsLoaded(true);
          return;
        }

        const stubs: Conversation[] = sessions.map(s => ({
          id:        s.session_id,
          title:     s.title || '未命名對話',
          messages:  [{ role: 'assistant' as const, content: GREETING, timestamp: new Date(s.updated_at) }],
          createdAt: new Date(s.updated_at),
          updatedAt: new Date(s.updated_at),
          isStub:    true,
        }));
        stubs.forEach(c => { sessionIds.current[c.id] = c.id; });
        setConversations(stubs);
        setSelectedConversationId(stubs[0].id);
        setSessionsLoaded(true);

        const detail = await chatAPI.getSession(stubs[0].id).catch(() => null);
        if (cancelled || !detail) return;
        const full = makeConvFromSession(detail);
        setConversations(prev => prev.map(c => c.id === full.id ? full : c));
        const lastMsg = [...full.messages].reverse().find(
          m => m.role === 'assistant' && (m.courseCards?.length ?? 0) > 0
        );
        if (lastMsg?.courseCards) setPanelCourses(lastMsg.courseCards);
      } catch {
        if (cancelled) return;
        createDefaultConversation();
        setSessionsLoaded(true);
      }
    })();

    return () => { cancelled = true; };
  }, [authLoading, liveAi.loading, user, showDemo, createDefaultConversation]);

  const updateConv = useCallback((id: string, updater: (c: Conversation) => Conversation) => {
    setConversations((prev) => prev.map((c) => (c.id === id ? updater(c) : c)));
  }, []);

  // ── 對話管理 ────────────────────────────────────────────────────────────
  const handleNewConversation = useCallback(() => {
    const nc: Conversation = {
      id: Date.now().toString(), title: '新對話',
      messages: [{ role: 'assistant', content: GREETING, timestamp: new Date() }],
      createdAt: new Date(), updatedAt: new Date(),
    };
    setConversations((prev) => [nc, ...prev]);
    setSelectedConversationId(nc.id);
    setInputMessage('');
    setIsMobileConversationOpen(false);
    setPanelCourses([]);
  }, []);

  const handleRenameConversation = useCallback((id: string, title: string) => {
    updateConv(id, (c) => ({ ...c, title }));
  }, [updateConv]);

  const handleDeleteConversation = (id: string) => {
    if (!window.confirm('確認要刪除這段對話嗎？此操作無法復原。')) return;
    const sid = sessionIds.current[id];
    if (sid) { chatAPI.clearSession(sid).catch(() => {}); delete sessionIds.current[id]; }
    setConversations((prev) => {
      const next = prev.filter((c) => c.id !== id);
      if (next.length === 0) {
        // 刪除最後一則：清空面板，建立新對話
        setPanelCourses([]);
        const nc: Conversation = {
          id: Date.now().toString(), title: '新對話',
          messages: [{ role: 'assistant', content: GREETING, timestamp: new Date() }],
          createdAt: new Date(), updatedAt: new Date(),
        };
        setSelectedConversationId(nc.id);
        return [nc];
      }
      if (selectedConversationId === id) {
        const nextConv = next[0];
        setSelectedConversationId(nextConv.id);
        const lastMsg = [...nextConv.messages].reverse().find(
          m => m.role === 'assistant' && (m.courseCards?.length ?? 0) > 0
        );
        setPanelCourses(lastMsg?.courseCards ?? []);
      }
      return next;
    });
    setInputMessage('');
  };

  // 選擇對話：stub 時 lazy load 完整詳情
  const handleSelectConversation = useCallback(async (id: string) => {
    setSelectedConversationId(id);
    setIsMobileConversationOpen(false);

    const conv = conversations.find(c => c.id === id);
    if (!conv) return;

    if (conv.isStub) {
      const detail = await chatAPI.getSession(id).catch(() => null);
      if (!detail) return;
      const full = makeConvFromSession(detail);
      setConversations(prev => prev.map(c => c.id === id ? full : c));
      const lastMsg = [...full.messages].reverse().find(
        m => m.role === 'assistant' && (m.courseCards?.length ?? 0) > 0
      );
      setPanelCourses(lastMsg?.courseCards ?? []);
      return;
    }

    const last = [...conv.messages].reverse().find(
      m => m.role === 'assistant' && !m.isStreaming && (m.courseCards?.length ?? 0) > 0
    );
    setPanelCourses(last?.courseCards ?? []);
  }, [conversations]);

  const handleShowMsgCourses = useCallback((msg: Message) => {
    setPanelCourses(msg.courseCards ?? []);
  }, []);

  // Ctrl+K / ⌘K 開新對話
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!showDemo && (e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        handleNewConversation();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleNewConversation, showDemo]);

  // ── 送出訊息（串流） ─────────────────────────────────────────────────────
  // sendText: 覆蓋 inputMessage；fromIdx: 從此索引截斷再送（編輯用）
  const doSend = (sendText?: string, fromIdx?: number) => {
    const text = (sendText !== undefined ? sendText : inputMessage).trim();
    if (!user || !liveAi.allowed || !text || !selectedConversation || isStreaming) return;

    if (sendText === undefined) setInputMessage('');
    const convId = selectedConversation.id;
    setIsStreaming(true);
    setActiveTools([]);
    setIsVerifying(false);
    activeTraceRef.current = { toolCalls: [], poolSize: 0 };

    const userMsg: Message   = { role: 'user',      content: text, timestamp: new Date() };
    const streamMsg: Message = { role: 'assistant',  content: '',   timestamp: new Date(), isStreaming: true };

    // 計算 streamIdx：如果有 fromIdx，訊息先截斷再加入，所以 streamMsg 在 fromIdx+1
    const baseCount = fromIdx !== undefined ? fromIdx : selectedConversation.messages.length;
    const streamIdx = baseCount + 1;

    updateConv(convId, (c) => {
      const base = fromIdx !== undefined ? c.messages.slice(0, fromIdx) : [...c.messages];
      return {
        ...c,
        updatedAt: new Date(),
        title: base.length === 1 ? text.slice(0, 30) : c.title,
        messages: [...base, userMsg, streamMsg],
      };
    });

    abortRef.current = chatStreamAPI.stream(
      text,
      {
        onToken: (tok) => {
          updateConv(convId, (c) => {
            const msgs = [...c.messages];
            if (msgs[streamIdx]) msgs[streamIdx] = { ...msgs[streamIdx], content: msgs[streamIdx].content + tok };
            return { ...c, messages: msgs };
          });
        },
        onToolStart: (tool, args) => {
          setActiveTools((prev) => [...prev, { name: tool, done: false }]);
          activeTraceRef.current.toolCalls.push({ tool, args, coursesFound: [], scores: [], scoreType: null, count: undefined });
        },
        onToolDone: (tool, count, coursesFound, scores, scoreType) => {
          setActiveTools((prev) =>
            prev.map((t) => (t.name === tool && !t.done ? { ...t, done: true, count } : t))
          );
          const calls = activeTraceRef.current.toolCalls;
          const last = [...calls].reverse().find((c) => c.tool === tool && c.count === undefined);
          if (last) {
            last.count = count;
            last.coursesFound = coursesFound ?? [];
            last.scores    = scores    ?? [];
            last.scoreType = scoreType ?? null;
          }
        },
        onVerifyStart: (poolSize) => {
          activeTraceRef.current.poolSize = poolSize;
          setIsVerifying(true);
        },
        onVerifyDone: (selected, filteredOut, method) => {
          setIsVerifying(false);
          (activeTraceRef.current as typeof activeTraceRef.current & { verifyResult?: unknown }).verifyResult = { selected, filteredOut, method };
        },
        onDone: (ev: StreamEvent) => {
          if (ev.session_id) sessionIds.current[convId] = ev.session_id;
          const cards = ev.course_cards ?? [];
          const tools = ev.tools_used   ?? [];

          const traceRef = activeTraceRef.current as typeof activeTraceRef.current & { verifyResult?: { selected: string[]; filteredOut: string[]; method?: 'tag' | 'llm' } };
          const debugTrace: DebugTrace = {
            toolCalls: traceRef.toolCalls,
            verify: traceRef.verifyResult
              ? { poolSize: traceRef.poolSize, ...traceRef.verifyResult }
              : null,
          };

          setPanelCourses(cards);

          updateConv(convId, (c) => {
            const msgs = [...c.messages];
            if (msgs[streamIdx]) {
              msgs[streamIdx] = {
                ...msgs[streamIdx],
                ...(ev.final_answer ? { content: ev.final_answer } : {}),
                isStreaming: false,
                courseCards: cards,
                toolsUsed:   tools,
                debugTrace,
              };
            }
            return { ...c, messages: msgs };
          });
          setIsStreaming(false);
          setIsVerifying(false);
          setActiveTools([]);
        },
        onError: (msg) => {
          updateConv(convId, (c) => {
            const msgs = [...c.messages];
            if (msgs[streamIdx]) {
              msgs[streamIdx] = {
                ...msgs[streamIdx],
                isStreaming: false,
                content: msgs[streamIdx].content || `抱歉，發生錯誤：${msg}`,
              };
            }
            return { ...c, messages: msgs };
          });
          setIsStreaming(false);
          setIsVerifying(false);
          setActiveTools([]);
        },
        onRestricted: (msg) => {
          // 後端判定目前帳號不能使用即時 AI：顯示說明而不是錯誤，並把輸入區換成說明元件
          liveAi.markRestricted(msg);
          updateConv(convId, (c) => {
            const msgs = [...c.messages];
            if (msgs[streamIdx]) {
              msgs[streamIdx] = { ...msgs[streamIdx], isStreaming: false, content: msgs[streamIdx].content || msg };
            }
            return { ...c, messages: msgs };
          });
          setIsStreaming(false);
          setIsVerifying(false);
          setActiveTools([]);
        },
      },
      sessionIds.current[convId] || undefined,
    );
  };

  const handleSendMessage = (e: FormEvent) => {
    e.preventDefault();
    doSend();
  };

  const handleAbort = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (!selectedConversation) return;
    const convId = selectedConversation.id;
    updateConv(convId, (c) => {
      const msgs = [...c.messages];
      const last = msgs.at(-1);
      if (last?.isStreaming) {
        msgs[msgs.length - 1] = {
          ...last,
          isStreaming: false,
          content: (last.content || '') + '…（已中止）',
        };
      }
      return { ...c, messages: msgs };
    });
    setIsStreaming(false);
    setIsVerifying(false);
    setActiveTools([]);
  };

  const handleSendEdit = () => {
    const text = editingContent.trim();
    if (!text || isStreaming) return;
    const fromIdx = editingMsgIdx;
    setEditingMsgIdx(-1);
    setEditingContent('');
    doSend(text, fromIdx);
  };

  const handleCancelEdit = () => {
    setEditingMsgIdx(-1);
    setEditingContent('');
  };

  return {
    liveAi,
    showDemo, demoListItems, demoQuestions,
    conversations, selectedConversationId, selectedConversation,
    inputMessage, setInputMessage,
    isMobileConversationOpen, setIsMobileConversationOpen,
    sessionsLoaded,
    isStreaming, activeTools, isVerifying,
    editingMsgIdx, setEditingMsgIdx,
    editingContent, setEditingContent,
    panelCourses,
    handleNewConversation, handleRenameConversation, handleDeleteConversation,
    handleSelectConversation, handleShowMsgCourses,
    doSend, handleSendMessage, handleAbort, handleSendEdit, handleCancelEdit,
  };
}

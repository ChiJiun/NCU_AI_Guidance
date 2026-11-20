import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { projectAPI } from '../../api/services';
import type { PdfConversationSummary } from '../../api/services';
import { useAuth } from '../../auth/AuthContext';
import { useLiveAiAccess } from '../../hooks/useLiveAiAccess';
import { demoAPI, type ResearchDemoCase } from '../../demo/demoCases';
import type { Project } from '../../types';
import {
  buildProjectPdfUrl,
  createWelcomeMessage,
  filterAndSortProjects,
  matchRecentChats,
  projectDepartments,
  projectYears,
} from './projectUtils';
import type { ChatMessage, RecentChat } from './projectUtils';

type MobileOutlineView = 'list' | 'detail';

/** 研究計畫 PDF 的網址（後端網址取自 VITE_API_URL） */
export function getPdfUrl(project: Project): string {
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  return buildProjectPdfUrl(project, apiUrl);
}

/**
 * 研究計畫頁的資料邏輯：計畫清單與篩選、最近對話、PDF 問答（串流、中止、編輯重送、
 * 對話切換與刪除），以及即時 AI 權限（LIVE_AI_RESTRICTED）處理。新舊版頁面共用這個 hook。
 */
export function useProjects({ demo = false }: { demo?: boolean } = {}) {
  const { user } = useAuth();
  const liveAi = useLiveAiAccess();
  // 展示版：後端明確不開放即時 AI 時，改看預先錄製的示範問答（只有傳入 demo 的頁面才會顯示）
  const showDemo = demo && liveAi.status === 'restricted';
  const [demoCases, setDemoCases] = useState<ResearchDemoCase[]>([]);
  const [activeDemoId, setActiveDemoId] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [viewMode, setViewMode] = useState<'outline' | 'pdf-chat'>('outline');
  const [mobileOutlineView, setMobileOutlineView] = useState<MobileOutlineView>('list');
  const [isMobileChatOpen, setIsMobileChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState<{ name: string; label: string } | null>(null);
  const [currentStage, setCurrentStage] = useState<string>('');
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [streamingText, setStreamingText] = useState('');
  const abortCtrlRef = useRef<AbortController | null>(null);
  const streamingTextRef = useRef('');
  const [loading, setLoading] = useState(true);
  const [pdfConversations, setPdfConversations] = useState<PdfConversationSummary[]>([]);
  const [filterYear, setFilterYear] = useState('');
  const [filterDept, setFilterDept] = useState('');
  const [filterTitle, setFilterTitle] = useState('');
  const [recentChats, setRecentChats] = useState<RecentChat[]>([]);
  const [leftPanelTab, setLeftPanelTab] = useState<'projects' | 'recent' | 'demo'>('projects');

  useEffect(() => {
    projectAPI
      .getProjects()
      .then((data) => {
        setProjects(data);
      })
      .catch((error) => {
        console.error('Failed to load projects:', error);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const cases = showDemo ? await demoAPI.researchCases() : [];
      if (cancelled) return;
      setDemoCases(cases);
      // 有示範就預設停在示範分頁；示範結束（例如開發團隊登入）時回到專題列表
      setLeftPanelTab((tab) => (cases.length > 0 ? 'demo' : tab === 'demo' ? 'projects' : tab));
    })();
    return () => { cancelled = true; };
  }, [showDemo]);

  useEffect(() => {
    if (!user || showDemo) { setRecentChats([]); return; }
    projectAPI.listRecentChats()
      .then(setRecentChats)
      .catch(() => {});
  }, [user, showDemo]);

  const years = useMemo(
    () => projectYears(projects),
    [projects]
  );

  const departments = useMemo(
    () => projectDepartments(projects),
    [projects]
  );

  const filteredProjects = useMemo(
    () => filterAndSortProjects(projects, filterYear, filterDept, filterTitle),
    [projects, filterYear, filterDept, filterTitle]
  );

  const matchedRecentChats = useMemo(
    () => matchRecentChats(recentChats, projects),
    [recentChats, projects]
  );

  const clearSelectedIfFiltered = (nextYear: string, nextDept: string) => {
    if (!selectedProject) return;
    const stillExists = projects.some(
      (p) =>
        p.id === selectedProject.id &&
        (!nextYear || p.year === nextYear) &&
        (!nextDept || p.department === nextDept),
    );
    if (stillExists) return;
    setSelectedProject(null);
    setChatMessages([]);
    setInputMessage('');
    setViewMode('outline');
    setMobileOutlineView('list');
    setIsMobileChatOpen(false);
  };

  const handleFilterYearChange = (year: string) => {
    setFilterYear(year);
    clearSelectedIfFiltered(year, filterDept);
  };

  const handleFilterDeptChange = (dept: string) => {
    setFilterDept(dept);
    clearSelectedIfFiltered(filterYear, dept);
  };

  const handleSelectProject = (project: Project) => {
    setSelectedProject(project);
    setChatMessages([createWelcomeMessage(project, showDemo)]);
    setActiveDemoId('');
    setInputMessage('');
    setViewMode('outline');
    setMobileOutlineView('detail');
    setIsMobileChatOpen(false);
    setThreadId(undefined);
    streamingTextRef.current = '';
    setStreamingText('');
    setChatLoading(false);
    setPdfConversations([]);
    abortCtrlRef.current?.abort();
    abortCtrlRef.current = null;
    if (user && !showDemo) {
      projectAPI.listConversations(project.id)
        .then((convs) => setPdfConversations(convs))
        .catch(() => {});
    }
  };

  /** 展示版：打開一組示範問答（切到該研究計畫的 PDF 與對話畫面） */
  const handleOpenDemo = (demoId: string) => {
    const demo = demoCases.find((c) => c.id === demoId);
    const project = demo && projects.find((p) => p.id === demo.project_id);
    if (!demo || !project) return;
    handleSelectProject(project);
    setActiveDemoId(demo.id);
    setChatMessages([
      createWelcomeMessage(project, true),
      ...demo.turns.flatMap((t): ChatMessage[] => [
        { role: 'user', content: t.user },
        { role: 'assistant', content: t.assistant, sources: t.sources?.length ? t.sources : undefined },
      ]),
    ]);
    setViewMode('pdf-chat');
    setIsMobileChatOpen(true);
  };

  // 首頁可以用 ?demo=<id> 直接開某一組示範（計畫與示範都載入後只觸發一次）
  const openedDemoFromUrl = useRef(false);
  useEffect(() => {
    if (openedDemoFromUrl.current || projects.length === 0 || demoCases.length === 0) return;
    openedDemoFromUrl.current = true;
    const wanted = new URLSearchParams(window.location.search).get('demo');
    if (wanted) handleOpenDemo(wanted);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects, demoCases]);

  const demoListItems = useMemo(() => demoCases.map((c) => ({
    id: c.id, title: c.title, category: c.category, summary: c.summary, reviewed: c.reviewed,
    meta: `${c.project_department}｜${c.project_title}`,
  })), [demoCases]);
  const activeDemo = demoCases.find((c) => c.id === activeDemoId) ?? null;
  const selectedProjectDemo = selectedProject
    ? demoCases.find((c) => c.project_id === selectedProject.id) ?? null
    : null;
  const demoQuestions = useMemo(
    () => demoCases.map((c) => ({ id: c.id, question: c.turns[0]?.user ?? c.title })),
    [demoCases],
  );

  const handleBackToOutline = () => {
    setViewMode('outline');
    setMobileOutlineView('detail');
    setIsMobileChatOpen(false);
  };

  const handleBackToProjectList = () => {
    setMobileOutlineView('list');
  };

  const handleOpenPdfChat = () => {
    if (!selectedProject) return;
    setViewMode('pdf-chat');
    setIsMobileChatOpen(false);
    if (chatMessages.length === 0) {
      setChatMessages([createWelcomeMessage(selectedProject, showDemo)]);
    }
  };

  const doSendProjectMessage = (msg: string, fromIdx?: number) => {
    if (!user || !liveAi.allowed || !selectedProject || chatLoading) return;
    setChatLoading(true);
    setStreamingText('');
    setChatMessages((prev) => {
      const base = fromIdx !== undefined ? prev.slice(0, fromIdx) : [...prev];
      return [...base, { role: 'user', content: msg }];
    });

    const ctrl = projectAPI.streamChat(
      selectedProject.id,
      msg,
      {
        onToken: (token) => {
          streamingTextRef.current += token;
          setStreamingText(streamingTextRef.current);
        },
        onReplace: (text) => {
          streamingTextRef.current = text;
          setStreamingText(text);
        },
        onSessionId: (id) => {
          setThreadId(id || undefined);
        },
        onAgentStart: (agent, label) => {
          setActiveAgent({ name: agent, label });
          setCurrentStage('');
        },
        onStage: (text) => {
          setCurrentStage(text);
        },
        onDone: (sessionId, _cancelled, sources) => {
          setActiveAgent(null);
          setCurrentStage('');
          const finalText = streamingTextRef.current;
          streamingTextRef.current = '';
          setStreamingText('');
          if (finalText) {
            setChatMessages((msgs) => [
              ...msgs,
              { role: 'assistant', content: finalText, sources: sources?.length ? sources : undefined },
            ]);
          }
          setChatLoading(false);
          const newThreadId = sessionId || undefined;
          setThreadId(newThreadId);
          abortCtrlRef.current = null;
          if (selectedProject && newThreadId) {
            projectAPI.listConversations(selectedProject.id)
              .then((convs) => setPdfConversations(convs))
              .catch(() => {});
          }
        },
        onError: (errMsg) => {
          setActiveAgent(null);
          setCurrentStage('');
          console.error('Project stream error:', errMsg);
          streamingTextRef.current = '';
          setStreamingText('');
          setChatMessages((prev) => [
            ...prev,
            { role: 'assistant', content: '目前暫時無法回應，請稍後再試一次。' },
          ]);
          setChatLoading(false);
          abortCtrlRef.current = null;
        },
        onRestricted: (restrictedMsg) => {
          // 後端判定目前帳號不能使用即時 AI：顯示說明而不是錯誤，並把輸入區換成說明元件
          liveAi.markRestricted(restrictedMsg);
          setActiveAgent(null);
          setCurrentStage('');
          streamingTextRef.current = '';
          setStreamingText('');
          setChatMessages((prev) => [...prev, { role: 'assistant', content: restrictedMsg }]);
          setChatLoading(false);
          abortCtrlRef.current = null;
        },
      },
      threadId,
    );
    abortCtrlRef.current = ctrl;
  };

  const handleSendMessage = (event: FormEvent) => {
    event.preventDefault();
    if (!inputMessage.trim()) return;
    const text = inputMessage.trim();
    setInputMessage('');
    doSendProjectMessage(text);
  };

  const handleSendEditedMessage = (newContent: string, fromIdx: number) => {
    doSendProjectMessage(newContent, fromIdx);
  };

  const handleCancelStream = () => {
    if (!abortCtrlRef.current || !selectedProject || !threadId) return;
    abortCtrlRef.current.abort();
    abortCtrlRef.current = null;
    if (threadId) projectAPI.cancelChat(selectedProject.id, threadId).catch(() => {});
    const finalText = streamingTextRef.current;
    streamingTextRef.current = '';
    setStreamingText('');
    if (finalText) {
      setChatMessages((msgs) => [...msgs, { role: 'assistant', content: finalText + '…（已中止）' }]);
    }
    setChatLoading(false);
    setActiveAgent(null);
    setCurrentStage('');
  };

  const handleNewPdfConversation = () => {
    if (!selectedProject) return;
    abortCtrlRef.current?.abort();
    abortCtrlRef.current = null;
    streamingTextRef.current = '';
    setStreamingText('');
    setChatLoading(false);
    setActiveAgent(null);
    setCurrentStage('');
    setThreadId(undefined);
    setChatMessages([createWelcomeMessage(selectedProject)]);
  };

  const handleSwitchPdfConversation = async (targetThreadId: string) => {
    if (!selectedProject || chatLoading || targetThreadId === threadId) return;
    abortCtrlRef.current?.abort();
    abortCtrlRef.current = null;
    streamingTextRef.current = '';
    setStreamingText('');
    setChatLoading(true);
    setThreadId(targetThreadId);
    try {
      const msgs = await projectAPI.loadConversationMessages(selectedProject.id, targetThreadId);
      setChatMessages([createWelcomeMessage(selectedProject), ...msgs]);
    } catch {
      setChatMessages([createWelcomeMessage(selectedProject)]);
    } finally {
      setChatLoading(false);
      setActiveAgent(null);
      setCurrentStage('');
    }
  };

  const handleDeletePdfConversation = async (targetThreadId: string) => {
    if (!selectedProject) return;
    if (!window.confirm('確定要刪除此對話嗎？')) return;
    try {
      await projectAPI.deleteConversation(selectedProject.id, targetThreadId);
    } catch {
      return;
    }
    setPdfConversations((prev) => prev.filter((c) => c.thread_id !== targetThreadId));
    if (targetThreadId === threadId) {
      streamingTextRef.current = '';
      setStreamingText('');
      setChatLoading(false);
      setActiveAgent(null);
      setCurrentStage('');
      abortCtrlRef.current?.abort();
      abortCtrlRef.current = null;
      setThreadId(undefined);
      setChatMessages([createWelcomeMessage(selectedProject)]);
    }
  };

  const handleSelectFromRecentChat = (project: Project, targetThreadId: string) => {
    abortCtrlRef.current?.abort();
    abortCtrlRef.current = null;
    streamingTextRef.current = '';
    setStreamingText('');
    setChatLoading(false);
    setActiveAgent(null);
    setCurrentStage('');
    setSelectedProject(project);
    setChatMessages([createWelcomeMessage(project, showDemo)]);
    setInputMessage('');
    setViewMode('outline');
    setMobileOutlineView('detail');
    setIsMobileChatOpen(false);
    setThreadId(targetThreadId);
    setPdfConversations([]);
    if (user) {
      projectAPI.listConversations(project.id)
        .then((convs) => setPdfConversations(convs))
        .catch(() => {});
    }
  };

  const handleContinueRecentChat = async () => {
    if (!selectedProject || !threadId) return;
    setViewMode('pdf-chat');
    setIsMobileChatOpen(false);
    setChatLoading(true);
    try {
      const msgs = await projectAPI.loadConversationMessages(selectedProject.id, threadId);
      setChatMessages([createWelcomeMessage(selectedProject), ...msgs]);
    } catch {
      setChatMessages([createWelcomeMessage(selectedProject)]);
    } finally {
      setChatLoading(false);
    }
  };

  return {
    liveAi,
    showDemo, demoListItems, demoQuestions, activeDemo, activeDemoId, selectedProjectDemo, handleOpenDemo,
    projects, loading,
    selectedProject,
    viewMode, mobileOutlineView,
    isMobileChatOpen, setIsMobileChatOpen,
    chatMessages, inputMessage, setInputMessage,
    chatLoading, activeAgent, currentStage,
    threadId, setThreadId, streamingText,
    pdfConversations,
    filterYear, filterDept, filterTitle, setFilterTitle,
    leftPanelTab, setLeftPanelTab,
    years, departments, filteredProjects, matchedRecentChats,
    handleFilterYearChange, handleFilterDeptChange,
    handleSelectProject, handleBackToOutline, handleBackToProjectList, handleOpenPdfChat,
    handleSendMessage, handleSendEditedMessage, handleCancelStream,
    handleNewPdfConversation, handleSwitchPdfConversation, handleDeletePdfConversation,
    handleSelectFromRecentChat, handleContinueRecentChat,
  };
}

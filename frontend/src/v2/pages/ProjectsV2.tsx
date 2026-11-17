import { useEffect, useMemo, useRef, useState } from 'react';
import { HiArrowLeft, HiArrowUp, HiCheck, HiPencil, HiPlus, HiSearch, HiStop, HiTrash, HiX } from 'react-icons/hi';
import type { PdfConversationSummary } from '../../api/services';
import { useAuth } from '../../auth/AuthContext';
import { GoogleMark } from '../../components/GoogleLoginButton';
import PdfViewer from '../../components/PdfViewer';
import { getDeptCollege } from '../../constants/colleges';
import { formatSourceLabels, groupDepartmentsByCollege } from '../../features/projects/projectUtils';
import type { ChatMessage } from '../../features/projects/projectUtils';
import { getPdfUrl, useProjects } from '../../features/projects/useProjects';
import type { Project } from '../../types';
import LiveAiGate from '../components/LiveAiGate';
import Markdown from '../components/Markdown';
import RovingGroup from '../components/RovingGroup';

/** 標題裡符合搜尋字的部分加底色 */
function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim().toLowerCase();
  const index = q ? text.toLowerCase().indexOf(q) : -1;
  if (index === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded-sm px-0.5" style={{ background: 'var(--v2-accent-soft)', color: 'inherit' }}>
        {text.slice(index, index + q.length)}
      </mark>
      {text.slice(index + q.length)}
    </>
  );
}

function ProjectRow({ project, current, query, onPick }: { project: Project; current: boolean; query: string; onPick: () => void }) {
  return (
    <li>
      <button type="button" className="v2-row !items-start !py-3" aria-current={current ? 'true' : undefined} onClick={onPick}>
        <span className="min-w-0 flex-1">
          <span className="v2-faint flex gap-2 text-xs">
            <span>{getDeptCollege(project.department)}</span>
            <span className="tabular-nums">{project.year}</span>
          </span>
          <span className="mt-0.5 line-clamp-2 block font-semibold leading-snug">
            <Highlight text={project.title} query={query} />
          </span>
          <span className="v2-muted mt-0.5 block truncate text-sm">
            {project.studentName} · {project.department}
          </span>
        </span>
      </button>
    </li>
  );
}

function ProjectDetail({
  project,
  hasThread,
  onContinue,
  onNewChat,
}: {
  project: Project;
  hasThread: boolean;
  onContinue: () => void;
  onNewChat: () => void;
}) {
  const sections: [string, string | undefined][] = [
    ['研究動機與問題', project.motivation || `這份研究計畫來自 ${project.department}，可作為了解研究主題、作品方向與成果呈現方式的參考。`],
    ['研究方法', project.method],
    ['研究成果', project.result],
  ];
  return (
    <article className="mx-auto max-w-3xl px-5 py-8 md:px-10 md:py-12">
      <p className="v2-faint flex flex-wrap gap-x-3 text-sm">
        <span>{getDeptCollege(project.department)}</span>
        <span className="tabular-nums">{project.year} 學年度</span>
      </p>
      <h2 className="v2-serif mt-2 text-3xl leading-tight md:text-4xl">{project.title}</h2>
      <p className="v2-muted mt-3">
        {project.studentName} · {project.department}
      </p>

      <div className="mt-6 flex flex-wrap gap-3">
        {hasThread && (
          <button type="button" className="v2-btn" onClick={onContinue}>
            繼續上次的對話
          </button>
        )}
        <button type="button" className={hasThread ? 'v2-btn v2-btn--ghost' : 'v2-btn'} onClick={onNewChat}>
          {hasThread ? '開新對話' : '閱讀 PDF 與提問'}
        </button>
      </div>

      <dl className="mt-10 space-y-8 border-t pt-8" style={{ borderColor: 'var(--v2-ink)' }}>
        {sections
          .filter(([, body]) => body)
          .map(([title, body]) => (
            <div key={title}>
              <dt className="font-semibold">{title}</dt>
              <dd className="v2-muted mt-2 leading-relaxed">{body}</dd>
            </div>
          ))}
        {project.tags && project.tags.length > 0 && (
          <div>
            <dt className="sr-only">領域標籤</dt>
            <dd className="flex flex-wrap gap-2">
              {project.tags.map((tag) => (
                <span key={tag} className="v2-tag">
                  {tag}
                </span>
              ))}
            </dd>
          </div>
        )}
      </dl>
    </article>
  );
}

function PdfPane({ project }: { project: Project }) {
  return project.pdfPath ? (
    <PdfViewer pdfUrl={getPdfUrl(project)} projectTitle={project.title} hideTitle />
  ) : (
    <div className="flex h-full items-center justify-center p-6">
      <p className="v2-muted">這份研究計畫沒有 PDF。</p>
    </div>
  );
}

/** 對話記錄（切換、刪除、開新對話） */
function ConversationMenu({
  conversations,
  activeThreadId,
  onNew,
  onSwitch,
  onDelete,
}: {
  conversations: PdfConversationSummary[];
  activeThreadId: string | undefined;
  onNew: () => void;
  onSwitch: (threadId: string) => void;
  onDelete: (threadId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const active = conversations.find((conversation) => conversation.thread_id === activeThreadId);
  return (
    <div ref={ref} className="relative min-w-0 flex-1">
      <button
        type="button"
        className="v2-navlink !max-w-full !px-1"
        aria-expanded={open}
        aria-controls="project-conversations"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="truncate">{active?.title ?? (activeThreadId ? '目前的對話' : '新對話')}</span>
        <span className="v2-num v2-faint ml-2 text-sm">{conversations.length}</span>
      </button>
      {open && (
        <div id="project-conversations" className="v2-panel absolute left-0 top-full z-30 mt-1 w-72 max-w-[calc(100vw-2rem)] overflow-hidden shadow-lg">
          <ul className="v2-scroll max-h-72">
            {conversations.map((conversation) => (
              <li key={conversation.thread_id} className="group relative">
                <button
                  type="button"
                  className="v2-row !pr-12"
                  aria-current={conversation.thread_id === activeThreadId ? 'true' : undefined}
                  onClick={() => {
                    setOpen(false);
                    onSwitch(conversation.thread_id);
                  }}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{conversation.title}</span>
                    <span className="v2-faint text-xs">{conversation.message_count} 則</span>
                  </span>
                </button>
                <button
                  type="button"
                  className="v2-iconbtn !absolute right-1 top-1/2 !h-9 !w-9 -translate-y-1/2"
                  aria-label={`刪除「${conversation.title}」`}
                  onClick={() => {
                    setOpen(false);
                    onDelete(conversation.thread_id);
                  }}
                >
                  <HiTrash className="h-4 w-4" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="v2-row !border-b-0 text-sm font-semibold"
            onClick={() => {
              setOpen(false);
              onNew();
            }}
          >
            <HiPlus className="h-4 w-4" aria-hidden="true" />
            新對話
          </button>
        </div>
      )}
    </div>
  );
}

function SourceTags({ sources }: { sources?: string[] }) {
  const labels = formatSourceLabels(sources);
  if (!labels.length) return null;
  return (
    <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs" aria-label="回答來源頁碼">
      <span className="v2-faint">來源</span>
      {labels.map((label) => (
        <span key={label} className="v2-tag !text-xs">
          {label}
        </span>
      ))}
    </p>
  );
}

export default function ProjectsV2() {
  const { user, loginWithGoogle } = useAuth();
  const {
    liveAi,
    loading,
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
  } = useProjects();
  const [editingIdx, setEditingIdx] = useState(-1);
  const [editingContent, setEditingContent] = useState('');
  const [loginFailed, setLoginFailed] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const deptGroups = useMemo(() => groupDepartmentsByCollege(departments, getDeptCollege), [departments]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [chatMessages, streamingText]);

  // 輸入框隨內容長高，最多約五行
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [inputMessage]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center" role="status">
        <span className="v2-spinner" aria-hidden="true" />
        <span className="sr-only">載入研究計畫</span>
      </div>
    );
  }

  const handleLogin = async () => {
    setLoginFailed(false);
    try {
      await loginWithGoogle();
    } catch {
      setLoginFailed(true);
    }
  };

  const showRecent = !!user && matchedRecentChats.length > 0;
  const tab = showRecent ? leftPanelTab : 'projects';

  // ── PDF 與問答 ──
  if (viewMode === 'pdf-chat' && selectedProject) {
    const lastUserIdx = chatMessages.reduce((found, message, index) => (message.role === 'user' ? index : found), -1);
    const canEdit = liveAi.allowed && !chatLoading;
    const startEdit = (index: number, message: ChatMessage) => {
      setEditingIdx(index);
      setEditingContent(message.content);
    };
    const cancelEdit = () => {
      setEditingIdx(-1);
      setEditingContent('');
    };
    const sendEdit = () => {
      const text = editingContent.trim();
      if (!text) return;
      const index = editingIdx;
      cancelEdit();
      handleSendEditedMessage(text, index);
    };

    const chat = (
      <section aria-label="研究計畫問答" className="flex min-h-0 flex-1 flex-col">
        {user && (pdfConversations.length > 0 || threadId) && (
          <div className="flex flex-none items-center border-b px-3 py-1" style={{ borderColor: 'var(--v2-line)' }}>
            <ConversationMenu
              conversations={pdfConversations}
              activeThreadId={threadId}
              onNew={handleNewPdfConversation}
              onSwitch={(id) => void handleSwitchPdfConversation(id)}
              onDelete={(id) => void handleDeletePdfConversation(id)}
            />
          </div>
        )}

        <div className="v2-scroll min-h-0 flex-1">
          <div className="space-y-6 px-4 py-6 md:px-6" aria-live="polite" aria-busy={chatLoading}>
            {chatMessages.map((message, index) => {
              if (message.role === 'user') {
                const editable = canEdit && index === lastUserIdx;
                if (editable && editingIdx === index) {
                  return (
                    <div key={index} className="ml-auto max-w-[90%]">
                      <textarea
                        autoFocus
                        rows={2}
                        className="v2-input resize-none"
                        aria-label="編輯問題"
                        value={editingContent}
                        onChange={(event) => setEditingContent(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                            event.preventDefault();
                            sendEdit();
                          }
                          if (event.key === 'Escape') cancelEdit();
                        }}
                      />
                      <div className="mt-2 flex justify-end gap-2">
                        <button type="button" className="v2-btn v2-btn--ghost v2-btn--sm" onClick={cancelEdit}>
                          取消
                        </button>
                        <button type="button" className="v2-btn v2-btn--sm" disabled={!editingContent.trim()} onClick={sendEdit}>
                          <HiCheck className="h-4 w-4" aria-hidden="true" />
                          送出
                        </button>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={index} className="group ml-auto flex max-w-[90%] items-start justify-end gap-1">
                    {editable && (
                      <button
                        type="button"
                        className="v2-iconbtn !h-9 !w-9 lg:opacity-0 lg:group-focus-within:opacity-100 lg:group-hover:opacity-100"
                        aria-label="編輯這個問題"
                        onClick={() => startEdit(index, message)}
                      >
                        <HiPencil className="h-4 w-4" aria-hidden="true" />
                      </button>
                    )}
                    <p className="whitespace-pre-line rounded-2xl rounded-br-sm px-4 py-2.5 text-white" style={{ background: 'var(--v2-ink)' }}>
                      {message.content}
                    </p>
                  </div>
                );
              }
              return (
                <div key={index}>
                  <Markdown text={message.content} />
                  <SourceTags sources={message.sources} />
                </div>
              );
            })}

            {chatLoading && streamingText && (
              <div>
                <Markdown text={streamingText} />
                <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse align-middle" style={{ background: 'var(--v2-ink)' }} aria-hidden="true" />
              </div>
            )}
            {chatLoading && (
              <p role="status" className="v2-muted flex items-center gap-2 text-sm">
                <span className="v2-spinner !h-4 !w-4" aria-hidden="true" />
                {activeAgent || currentStage ? (
                  <span>
                    {activeAgent?.label}
                    {activeAgent && currentStage && ' · '}
                    {currentStage}
                  </span>
                ) : (
                  <span className="sr-only">回答中</span>
                )}
              </p>
            )}
            <div ref={endRef} />
          </div>
        </div>

        <div className="flex-none border-t px-4 py-3 md:px-6" style={{ borderColor: 'var(--v2-line)' }}>
          {!user ? (
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="v2-btn" onClick={handleLogin}>
                <GoogleMark />
                登入後提問
              </button>
              {loginFailed && (
                <p role="alert" className="text-sm" style={{ color: 'var(--v2-danger)' }}>
                  登入失敗，請再試一次
                </p>
              )}
            </div>
          ) : (
            <LiveAiGate liveAi={liveAi} assistant="research">
              <form onSubmit={handleSendMessage} className="flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  rows={1}
                  className="v2-input resize-none"
                  aria-label="針對這份研究計畫提問"
                  placeholder="想了解這份研究的什麼？"
                  value={inputMessage}
                  disabled={chatLoading}
                  onChange={(event) => setInputMessage(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                />
                {chatLoading ? (
                  <button type="button" className="v2-btn v2-btn--ghost !w-11 !px-0" aria-label="停止回答" onClick={handleCancelStream}>
                    <HiStop className="h-5 w-5" aria-hidden="true" />
                  </button>
                ) : (
                  <button type="submit" className="v2-btn !w-11 !px-0" aria-label="送出" disabled={!inputMessage.trim()}>
                    <HiArrowUp className="h-5 w-5" aria-hidden="true" />
                  </button>
                )}
              </form>
            </LiveAiGate>
          )}
        </div>
      </section>
    );

    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex flex-none items-center gap-2 border-b px-2 py-1 md:px-4" style={{ borderColor: 'var(--v2-line)' }}>
          <button type="button" className="v2-iconbtn" aria-label="返回研究計畫介紹" onClick={handleBackToOutline}>
            <HiArrowLeft className="h-5 w-5" aria-hidden="true" />
          </button>
          <h1 className="min-w-0 flex-1 truncate font-semibold">{selectedProject.title}</h1>
          <RovingGroup role="tablist" aria-label="顯示" className="v2-seg flex-none lg:!hidden">
            <button type="button" role="tab" aria-selected={!isMobileChatOpen} className="!min-h-9 !px-3 !text-sm" onClick={() => setIsMobileChatOpen(false)}>
              PDF
            </button>
            <button type="button" role="tab" aria-selected={isMobileChatOpen} className="!min-h-9 !px-3 !text-sm" onClick={() => setIsMobileChatOpen(true)}>
              提問
            </button>
          </RovingGroup>
        </div>
        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_28rem]">
          {/* 手機一次顯示一欄（PDF 或提問），桌面並排 */}
          <div className={`min-h-0 ${isMobileChatOpen ? 'hidden lg:block' : ''}`} style={{ background: 'var(--v2-paper-2)' }}>
            <PdfPane project={selectedProject} />
          </div>
          <div className={`min-h-0 flex-col border-l ${isMobileChatOpen ? 'flex' : 'hidden lg:flex'}`} style={{ borderColor: 'var(--v2-line)' }}>
            {chat}
          </div>
        </div>
      </div>
    );
  }

  // ── 清單與介紹 ──
  const list = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-none space-y-2 border-b p-3" style={{ borderColor: 'var(--v2-line)' }}>
        <div className="relative">
          <HiSearch className="v2-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" aria-hidden="true" />
          <input
            type="search"
            className="v2-input !pl-9 !pr-10"
            aria-label="搜尋研究計畫標題"
            placeholder="搜尋標題"
            value={filterTitle}
            onChange={(event) => setFilterTitle(event.target.value)}
          />
          {filterTitle && (
            <button type="button" className="v2-iconbtn !absolute right-0 top-0" aria-label="清除搜尋" onClick={() => setFilterTitle('')}>
              <HiX className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
        <div className="grid grid-cols-[6.5rem_1fr] gap-2">
          <select className="v2-input !px-2" aria-label="學年度" value={filterYear} onChange={(event) => handleFilterYearChange(event.target.value)}>
            <option value="">全部年度</option>
            {years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
          <select className="v2-input min-w-0 !px-2" aria-label="系所" value={filterDept} onChange={(event) => handleFilterDeptChange(event.target.value)}>
            <option value="">全部系所</option>
            {deptGroups.map(([college, depts]) => (
              <optgroup key={college} label={college}>
                {depts.map((dept) => (
                  <option key={dept} value={dept}>
                    {dept}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
        <div className="flex min-h-9 items-center justify-between gap-2">
          {showRecent ? (
            <RovingGroup role="tablist" aria-label="清單" className="v2-seg">
              <button type="button" role="tab" aria-selected={tab === 'projects'} className="!min-h-8 !px-3 !text-sm" onClick={() => setLeftPanelTab('projects')}>
                研究計畫
              </button>
              <button type="button" role="tab" aria-selected={tab === 'recent'} className="!min-h-8 !px-3 !text-sm" onClick={() => setLeftPanelTab('recent')}>
                最近對話
              </button>
            </RovingGroup>
          ) : (
            <span />
          )}
          {tab === 'projects' && (
            <span className="v2-faint text-sm" aria-live="polite">
              <span className="v2-num">{filteredProjects.length}</span> 筆
            </span>
          )}
        </div>
      </div>

      <ul className="v2-scroll min-h-0 flex-1" aria-label={tab === 'recent' ? '最近對話' : '研究計畫'}>
        {tab === 'recent'
          ? matchedRecentChats.map((recent) => (
              <li key={recent.thread_id}>
                <button
                  type="button"
                  className="v2-row !items-start !py-3"
                  aria-current={selectedProject?.id === recent.project.id && threadId === recent.thread_id ? 'true' : undefined}
                  onClick={() => handleSelectFromRecentChat(recent.project, recent.thread_id)}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold">{recent.project.title}</span>
                    <span className="v2-muted block truncate text-sm">{recent.title}</span>
                    {recent.created_at && <span className="v2-faint text-xs">{new Date(recent.created_at).toLocaleDateString('zh-TW')}</span>}
                  </span>
                </button>
              </li>
            ))
          : filteredProjects.map((project) => (
              <ProjectRow
                key={project.id}
                project={project}
                query={filterTitle}
                current={selectedProject?.id === project.id}
                onPick={() => handleSelectProject(project)}
              />
            ))}
        {tab === 'projects' && filteredProjects.length === 0 && <li className="v2-muted p-4">沒有符合條件的研究計畫。</li>}
      </ul>
    </div>
  );

  const showDetailOnMobile = mobileOutlineView === 'detail' && !!selectedProject;

  return (
    <div className="grid h-full min-h-0 lg:grid-cols-[24rem_1fr]">
      <h1 className="sr-only">研究計畫</h1>
      <aside aria-label="研究計畫清單" className={`min-h-0 flex-col border-r ${showDetailOnMobile ? 'hidden lg:flex' : 'flex'}`} style={{ borderColor: 'var(--v2-line)' }}>
        {list}
      </aside>

      <section aria-label="研究計畫介紹" className={`v2-scroll min-h-0 ${showDetailOnMobile ? 'block' : 'hidden lg:block'}`}>
        {selectedProject ? (
          <>
            <div className="px-2 pt-2 lg:hidden">
              <button type="button" className="v2-navlink !px-2" onClick={handleBackToProjectList}>
                <HiArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
                研究計畫清單
              </button>
            </div>
            <ProjectDetail
              project={selectedProject}
              hasThread={!!threadId}
              onContinue={() => void handleContinueRecentChat()}
              onNewChat={() => {
                setThreadId(undefined);
                handleOpenPdfChat();
              }}
            />
          </>
        ) : (
          <div className="v2-hero-art !relative h-full opacity-50" aria-hidden="true">
            <div className="v2-hero-static" />
          </div>
        )}
      </section>
    </div>
  );
}

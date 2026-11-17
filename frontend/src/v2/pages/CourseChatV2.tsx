import { useEffect, useRef, useState } from 'react';
import { HiArrowUp, HiCheck, HiPencil, HiPlus, HiStop, HiTrash, HiViewList, HiX } from 'react-icons/hi';
import { useAuth } from '../../auth/AuthContext';
import CourseDetailModal from '../../components/CourseDetailModal';
import DebugTracePanel from '../../components/DebugTracePanel';
import { GoogleMark } from '../../components/GoogleLoginButton';
import HighlightedAnswer from '../../components/HighlightedAnswer';
import { TOOL_LABELS } from '../../features/courseChat/toolLabels';
import { formatTime, useCourseChat } from '../../features/courseChat/useCourseChat';
import type { CourseCard } from '../../types';
import LiveAiGate from '../components/LiveAiGate';
import V2Dialog from '../components/V2Dialog';

/** 推薦課程清單（右欄；手機在對話下方展開） */
function CourseList({ courses, onPick }: { courses: CourseCard[]; onPick: (course: CourseCard) => void }) {
  return (
    <ol>
      {courses.map((course, index) => (
        <li key={`${course.code}-${index}`}>
          <button type="button" className="v2-row !items-start !py-3" onClick={() => onPick(course)}>
            <span className="v2-num v2-faint w-5 flex-none pt-0.5 text-sm">{index + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="block font-semibold leading-snug">{course.name}</span>
              <span className="v2-muted flex flex-wrap gap-x-2 text-sm">
                {course.dept && <span>{course.dept}</span>}
                {course.credits ? <span>{course.credits} 學分</span> : null}
                {course.type && <span className={course.type === '必修' ? 'v2-accent font-semibold' : ''}>{course.type}</span>}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}

export default function CourseChatV2() {
  const { user, loginWithGoogle } = useAuth();
  const {
    liveAi,
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
  } = useCourseChat();
  const [openCourse, setOpenCourse] = useState<CourseCard | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null);
  const [loginFailed, setLoginFailed] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const messageCount = selectedConversation?.messages.length ?? 0;
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [messageCount, isStreaming]);

  // 輸入框隨內容長高，最多約五行
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [inputMessage]);

  if (!sessionsLoaded) {
    return (
      <div className="flex h-full items-center justify-center" role="status">
        <span className="v2-spinner" aria-hidden="true" />
        <span className="sr-only">載入對話記錄</span>
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

  const commitRename = () => {
    if (renaming && renaming.title.trim()) handleRenameConversation(renaming.id, renaming.title.trim());
    setRenaming(null);
  };

  const messages = selectedConversation?.messages ?? [];
  const lastUserIdx = messages.reduce((found, message, index) => (message.role === 'user' ? index : found), -1);
  const waitingForFirstToken = isStreaming && activeTools.length === 0 && !messages.at(-1)?.content;

  const history = (
    <nav aria-label="對話記錄" className="flex min-h-0 flex-1 flex-col">
      <div className="flex-none p-3">
        <button type="button" className="v2-btn w-full" onClick={handleNewConversation} title="Ctrl+K">
          <HiPlus className="h-4 w-4" aria-hidden="true" />
          新對話
        </button>
      </div>
      <ul className="v2-scroll min-h-0 flex-1">
        {conversations.map((conversation) => {
          const current = conversation.id === selectedConversationId;
          if (renaming?.id === conversation.id) {
            return (
              <li key={conversation.id} className="flex items-center gap-1 border-b px-2 py-1.5" style={{ borderColor: 'var(--v2-line)' }}>
                <input
                  autoFocus
                  className="v2-input !min-h-9 !py-1 !text-sm"
                  aria-label="對話名稱"
                  value={renaming.title}
                  onChange={(event) => setRenaming({ id: conversation.id, title: event.target.value })}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') commitRename();
                    if (event.key === 'Escape') {
                      // 只取消重新命名，不要連手機的對話記錄抽屜一起關掉
                      event.stopPropagation();
                      setRenaming(null);
                    }
                  }}
                  onBlur={commitRename}
                />
              </li>
            );
          }
          return (
            <li key={conversation.id} className="group relative">
              <button
                type="button"
                className="v2-row !pr-20"
                aria-current={current ? 'true' : undefined}
                onClick={() => void handleSelectConversation(conversation.id)}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[0.9375rem] font-medium">{conversation.title}</span>
                  <span className="v2-faint text-xs">{formatTime(conversation.updatedAt)}</span>
                </span>
              </button>
              <div className="absolute right-1 top-1/2 flex -translate-y-1/2 opacity-100 lg:opacity-0 lg:group-focus-within:opacity-100 lg:group-hover:opacity-100">
                <button
                  type="button"
                  className="v2-iconbtn !h-9 !w-9"
                  aria-label={`重新命名「${conversation.title}」`}
                  onClick={() => setRenaming({ id: conversation.id, title: conversation.title })}
                >
                  <HiPencil className="h-4 w-4" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className="v2-iconbtn !h-9 !w-9"
                  aria-label={`刪除「${conversation.title}」`}
                  onClick={() => handleDeleteConversation(conversation.id)}
                >
                  <HiTrash className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </nav>
  );

  return (
    <div className="grid h-full min-h-0 lg:grid-cols-[16rem_1fr_19rem]">
      <h1 className="sr-only">課程助理</h1>

      {/* 對話記錄：桌面固定在左側，手機是抽屜 */}
      <aside className="hidden min-h-0 flex-col border-r lg:flex" style={{ borderColor: 'var(--v2-line)' }}>
        {history}
      </aside>
      {isMobileConversationOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/30" aria-hidden="true" onClick={() => setIsMobileConversationOpen(false)} />
          <V2Dialog
            aria-label="對話記錄"
            onClose={() => setIsMobileConversationOpen(false)}
            className="v2-rise absolute inset-y-0 left-0 flex w-[85%] max-w-xs flex-col shadow-2xl"
            style={{ background: 'var(--v2-paper)' }}
          >
            <div className="flex flex-none justify-end p-1">
              <button type="button" className="v2-iconbtn" aria-label="關閉" onClick={() => setIsMobileConversationOpen(false)}>
                <HiX className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            {history}
          </V2Dialog>
        </div>
      )}

      {/* 對話 */}
      <section aria-label="對話" className="flex min-h-0 min-w-0 flex-col">
        <div className="flex flex-none items-center gap-1 border-b px-2 py-1 lg:hidden" style={{ borderColor: 'var(--v2-line)' }}>
          <button type="button" className="v2-iconbtn" aria-label="對話記錄" onClick={() => setIsMobileConversationOpen(true)}>
            <HiViewList className="h-5 w-5" aria-hidden="true" />
          </button>
          <p className="min-w-0 flex-1 truncate font-semibold">{selectedConversation?.title}</p>
          <button type="button" className="v2-iconbtn" aria-label="新對話" onClick={handleNewConversation}>
            <HiPlus className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="v2-scroll min-h-0 flex-1">
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-6 md:px-8" aria-live="polite" aria-busy={isStreaming}>
            {messages.map((message, index) => {
              if (message.role === 'user') {
                const canEdit = index === lastUserIdx && !isStreaming && liveAi.allowed;
                if (canEdit && editingMsgIdx === index) {
                  return (
                    <div key={index} className="ml-auto max-w-[85%]">
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
                            handleSendEdit();
                          }
                          if (event.key === 'Escape') handleCancelEdit();
                        }}
                      />
                      <div className="mt-2 flex justify-end gap-2">
                        <button type="button" className="v2-btn v2-btn--ghost v2-btn--sm" onClick={handleCancelEdit}>
                          取消
                        </button>
                        <button type="button" className="v2-btn v2-btn--sm" disabled={!editingContent.trim()} onClick={handleSendEdit}>
                          <HiCheck className="h-4 w-4" aria-hidden="true" />
                          送出
                        </button>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={index} className="group ml-auto flex max-w-[85%] items-start justify-end gap-1">
                    {canEdit && (
                      <button
                        type="button"
                        className="v2-iconbtn !h-9 !w-9 lg:opacity-0 lg:group-focus-within:opacity-100 lg:group-hover:opacity-100"
                        aria-label="編輯這個問題"
                        onClick={() => {
                          setEditingMsgIdx(index);
                          setEditingContent(message.content);
                        }}
                      >
                        <HiPencil className="h-4 w-4" aria-hidden="true" />
                      </button>
                    )}
                    <p
                      className="whitespace-pre-line rounded-2xl rounded-br-sm px-4 py-2.5 text-white"
                      style={{ background: 'var(--v2-ink)' }}
                      title={message.timestamp.toLocaleString('zh-TW')}
                    >
                      {message.content}
                    </p>
                  </div>
                );
              }

              const cards = message.courseCards ?? [];
              // HighlightedAnswer 自帶 markdown 樣式，不再套 .v2-prose，避免兩套規則互相覆蓋
              return (
                <div key={index}>
                  <HighlightedAnswer text={message.content} courseCards={cards} onCourseClick={setOpenCourse} />
                  {message.isStreaming && (
                    <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse align-middle" style={{ background: 'var(--v2-ink)' }} aria-hidden="true" />
                  )}
                  {!message.isStreaming && cards.length > 0 && (
                    <div className="not-prose mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <button type="button" className="v2-btn v2-btn--ghost v2-btn--sm" onClick={() => handleShowMsgCourses(message)}>
                        <span className="v2-num">{cards.length}</span> 門課
                      </button>
                      {(message.toolsUsed?.length ?? 0) > 0 && (
                        <span className="v2-faint text-xs">{message.toolsUsed!.map((tool) => TOOL_LABELS[tool] ?? tool).join(' · ')}</span>
                      )}
                    </div>
                  )}
                  {!message.isStreaming && message.debugTrace && <DebugTracePanel trace={message.debugTrace} />}
                </div>
              );
            })}

            {isStreaming && activeTools.length > 0 && (
              <ul className="v2-muted space-y-1 text-sm" aria-label="查詢進度">
                {activeTools.map((tool, index) => (
                  <li key={index} className="flex items-center gap-2">
                    {tool.done ? (
                      <HiCheck className="h-4 w-4" style={{ color: 'var(--v2-ok)' }} aria-hidden="true" />
                    ) : (
                      <span className="v2-spinner !h-4 !w-4" aria-hidden="true" />
                    )}
                    <span className={tool.done ? 'v2-faint' : ''}>
                      {TOOL_LABELS[tool.name] ?? tool.name}
                      {tool.done && tool.count != null && <span className="v2-num"> {tool.count}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {isVerifying && (
              <p className="v2-muted flex items-center gap-2 text-sm" role="status">
                <span className="v2-spinner !h-4 !w-4" aria-hidden="true" />
                驗證推薦課程
              </p>
            )}
            {waitingForFirstToken && (
              <div role="status" className="flex items-center gap-2">
                <span className="v2-spinner" aria-hidden="true" />
                <span className="sr-only">回答中</span>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {panelCourses.length > 0 && (
            <section aria-label="推薦課程" className="border-t lg:hidden" style={{ borderColor: 'var(--v2-line)' }}>
              <CourseList courses={panelCourses} onPick={setOpenCourse} />
            </section>
          )}
        </div>

        <div className="flex-none border-t px-4 py-3 md:px-8" style={{ borderColor: 'var(--v2-line)' }}>
          <div className="mx-auto max-w-3xl">
            {!user ? (
              <div className="flex flex-wrap items-center gap-3">
                <button type="button" className="v2-btn" onClick={handleLogin}>
                  <GoogleMark />
                  登入後開始對話
                </button>
                {loginFailed && (
                  <p role="alert" className="text-sm" style={{ color: 'var(--v2-danger)' }}>
                    登入失敗，請再試一次
                  </p>
                )}
              </div>
            ) : (
              <LiveAiGate liveAi={liveAi} assistant="course">
                <form onSubmit={handleSendMessage} className="flex items-end gap-2">
                  <textarea
                    ref={inputRef}
                    rows={1}
                    className="v2-input resize-none"
                    aria-label="問課程助理"
                    placeholder="想修什麼樣的課？"
                    value={inputMessage}
                    disabled={isStreaming}
                    onChange={(event) => setInputMessage(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                        event.preventDefault();
                        doSend();
                      }
                    }}
                  />
                  {isStreaming ? (
                    <button type="button" className="v2-btn v2-btn--ghost !w-11 !px-0" aria-label="停止回答" onClick={handleAbort}>
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
        </div>
      </section>

      {/* 推薦課程（桌面） */}
      <aside aria-label="推薦課程" className="v2-scroll hidden min-h-0 border-l lg:block" style={{ borderColor: 'var(--v2-line)' }}>
        {panelCourses.length > 0 ? (
          <CourseList courses={panelCourses} onPick={setOpenCourse} />
        ) : (
          <div className="v2-hero-art !relative h-full opacity-50" aria-hidden="true">
            <div className="v2-hero-static" />
          </div>
        )}
      </aside>

      {openCourse && <CourseDetailModal course={openCourse} onClose={() => setOpenCourse(null)} />}
    </div>
  );
}

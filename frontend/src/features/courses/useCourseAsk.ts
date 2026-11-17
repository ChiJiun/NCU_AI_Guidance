import { useEffect, useState } from 'react';
import { courseAPI } from '../../api/services';
import { apiErrorDisplayMessage, liveAiRestrictedMessageFromError } from '../../api/liveAi';
import { useLiveAiAccess } from '../../hooks/useLiveAiAccess';
import type { Course } from '../../types';


// detail 可能是物件或陣列，統一轉成字串，避免把物件當成 React child 渲染而讓頁面崩潰
const getApiErrorMessage = (error: unknown) =>
  apiErrorDisplayMessage(error, 'AI 課程助理暫時無法回答，請稍後再試。');

export const QUICK_ACTIONS = [
  { id: 'translate', label: '翻成中文', prompt: '請把這門課的課程目標與課程內容翻譯成繁體中文，保持原本的架構。' },
  { id: 'simplify', label: '高中生版本', prompt: '請用高中生能理解的語言，整理這門課在學什麼、有什麼實際用途。' },
  { id: 'connect', label: '連結高中知識', prompt: '這門課的核心概念可以對應到高中哪些科目的哪些單元？請舉例說明。' },
  { id: 'fit', label: '我適合修嗎', prompt: '這門課適合什麼樣背景的學生？需要哪些先備知識？有推薦先修的課程嗎？' },
];

/**
 * 「針對單一門課問 AI」的資料邏輯：提問、回答、錯誤，以及即時 AI 權限（LIVE_AI_RESTRICTED）處理。
 * 新舊版的課程詳情共用這個 hook。
 */
export function useCourseAsk(course: Course | null) {
  const [askOpen, setAskOpen] = useState(false);
  const [askQuestion, setAskQuestion] = useState('');
  const [askLastQuestion, setAskLastQuestion] = useState('');
  const [askAnswer, setAskAnswer] = useState('');
  const [askError, setAskError] = useState('');
  const [askLoading, setAskLoading] = useState(false);
  const liveAi = useLiveAiAccess();
  const courseIdentity = course ? `${course.serial_no}-${course.course_id}` : '';

  const resetAskState = () => {
    setAskQuestion('');
    setAskLastQuestion('');
    setAskAnswer('');
    setAskError('');
    setAskLoading(false);
  };

  useEffect(() => {
    void (async () => {
      await Promise.resolve();
      setAskOpen(false);
      resetAskState();
    })();
  }, [courseIdentity]);

  const closeAsk = () => {
    setAskOpen(false);
    resetAskState();
  };

  const submitQuestion = async (question: string) => {
    if (!course || !liveAi.allowed) return;
    setAskLoading(true);
    setAskError('');
    setAskAnswer('');
    setAskLastQuestion(question);
    try {
      const response = await courseAPI.askCourse(course.course_id, question);
      setAskAnswer(response.answer);
      if (response.warnings.length > 0) {
        setAskError(response.warnings.join(' '));
      }
    } catch (error) {
      const restricted = liveAiRestrictedMessageFromError(error);
      if (restricted !== null) {
        // 後端判定目前帳號不能使用即時 AI：輸入區換成說明元件（說明裡已有同一句話，不再另外顯示錯誤）
        liveAi.markRestricted(restricted);
      } else {
        setAskError(getApiErrorMessage(error));
      }
    } finally {
      setAskLoading(false);
    }
  };

  return {
    askOpen, setAskOpen,
    askQuestion, setAskQuestion,
    askLastQuestion, askAnswer,
    askError, setAskError,
    askLoading,
    liveAi,
    resetAskState, closeAsk, submitQuestion,
  };
}

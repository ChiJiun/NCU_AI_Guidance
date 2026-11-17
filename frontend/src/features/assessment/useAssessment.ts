import { useState } from 'react';
import { assessmentAPI } from '../../api/services';
import type { Question, Answer, AssessmentResult, AssessmentMode } from '../../types';

// 文理分組與系所名稱對照由後端統一處理（backend/app/services/department_names.py）：
// - 每張題卡帶 tracks（'liberal' / 'science'），高二依此分組
// - 高三 filter-by-subjects 直接回傳題庫中的系所名稱
export type Track = 'liberal' | 'science';

export interface UseAssessmentOptions {
  /** 載入或提交失敗時的通知方式；預設沿用舊版的 alert */
  notify?: (message: string) => void;
}

/**
 * 興趣量表的資料流程（抽題、作答、計分、高三再測一輪）。
 * 新舊版頁面共用這個 hook，各自只負責畫面。
 */
export function useAssessment({ notify = (message) => window.alert(message) }: UseAssessmentOptions = {}) {
  const [mode, setMode] = useState<AssessmentMode>('grade1');
  const [trackType, setTrackType] = useState<Track | null>(null); // 高二模式的文理分組
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]); // 高三模式的學測科目選擇
  const [started, setStarted] = useState(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Map<string, number>>(new Map());
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AssessmentResult | null>(null);
  // 高三：可報名的學系、前幾輪的作答（再測一輪時保留，最後一起計分）
  const [eligibleUnits, setEligibleUnits] = useState<string[]>([]);
  const [prevAnswers, setPrevAnswers] = useState<Map<string, number>>(new Map());
  const [prevDepts, setPrevDepts] = useState<string[]>([]);

  // 抽題在後端：推薦單位是大學部學系（研究所題卡併入所屬學系），每個學系 1 張題卡。
  // 高一 10 張；高二文組 8 張、理組 16 張；高三每輪最多 16 張，沒出到的學系可再測一輪。
  // 每輪開始時產生一個 seed，題目存在 state，作答期間不會變；重新測驗會換一組題卡。
  const loadQuestions = async (exclude?: string[]) => {
    try {
      setLoading(true);
      setQuestions([]);
      const seed = Math.floor(Math.random() * 2 ** 31);
      const data = await assessmentAPI.getQuestions(mode, {
        seed,
        track: mode === 'grade2' && trackType ? trackType : undefined,
        subjects: mode === 'grade3' ? selectedSubjects : undefined,
        exclude,
      });
      if (data.length === 0) {
        notify('依你選擇的學測科目，目前沒有可報名的科系題卡，請調整科目後再試');
        setStarted(false);
        return;
      }
      setQuestions(data);
      setCurrentIndex(0);
      setAnswers(new Map());
      setResult(null);
    } catch (error) {
      console.error('載入題目失敗:', error);
      notify('載入題目失敗，請稍後再試');
      setStarted(false);
    } finally {
      setLoading(false);
    }
  };

  const handleStart = async () => {
    // 高二模式需要先選擇文理分組
    if (mode === 'grade2' && !trackType) {
      return;
    }
    // 高三模式需要先選擇學測科目（後端只出「採計科目都有考到」的科系）
    if (mode === 'grade3' && selectedSubjects.length === 0) {
      return;
    }

    setStarted(true);
    setPrevAnswers(new Map());
    setPrevDepts([]);
    setEligibleUnits([]);
    if (mode === 'grade3') {
      try {
        const eligible = await assessmentAPI.filterBySubjects(selectedSubjects);
        setEligibleUnits(eligible.units ?? []);
      } catch (error) {
        console.error('篩選科系失敗:', error); // 只影響「未涵蓋學系」提示，題目照常載入
      }
    }
    await loadQuestions();
  };

  // 高三再測一輪：保留這一輪的作答，只出還沒作答過的學系
  const handleNextRound = async () => {
    const done = [...new Set([...prevDepts, ...questions.map(q => q.department)])];
    setPrevAnswers(new Map([...prevAnswers, ...answers]));
    setPrevDepts(done);
    await loadQuestions(done);
  };

  const getQuestionCount = (question: Question) => question.questions?.length || 1;
  const getAnswerKey = (questionId: string, questionIndex: number) => `${questionId}::${questionIndex}`;

  const handleScore = (score: number, questionIndex = 0) => {
    const newAnswers = new Map(answers);
    newAnswers.set(getAnswerKey(questions[currentIndex].id, questionIndex), score);
    setAnswers(newAnswers);
  };

  const handleNext = () => {
    if (currentIndex < questions.length - 1) {
      setCurrentIndex(currentIndex + 1);
    }
  };

  const handlePrevious = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
    }
  };

  const handleSubmit = async () => {
    try {
      setLoading(true);
      const allAnswers = new Map([...prevAnswers, ...answers]);
      const answersArray: Answer[] = Array.from(allAnswers.entries()).map(
        ([answerKey, score]) => ({
          questionId: answerKey.split('::')[0],
          score,
        })
      );

      const result = await assessmentAPI.submitAnswers(mode, answersArray);
      setResult(result);
    } catch (error) {
      console.error('提交失敗:', error);
      notify('提交失敗，請稍後再試');
    } finally {
      setLoading(false);
    }
  };

  // 判斷文組或理組（高一模式）：文 / 理組各 5 張題卡，比較兩組平均分（後端 trackScores）；
  // 平均相同時看排名第一的科系屬哪一組
  const determineTrack = (): Track | null => {
    if (!result) return null;
    const liberal = result.trackScores?.liberal ?? 0;
    const science = result.trackScores?.science ?? 0;
    if (liberal !== science) return liberal > science ? 'liberal' : 'science';
    const top = result.departments[0];
    const topTracks = questions.find(q => q.department === top?.name)?.tracks ?? [];
    return topTracks.includes('liberal') ? 'liberal' : 'science';
  };

  return {
    mode, setMode,
    trackType, setTrackType,
    selectedSubjects, setSelectedSubjects,
    started, setStarted,
    questions,
    currentIndex,
    answers,
    loading,
    result, setResult,
    eligibleUnits,
    prevDepts,
    handleStart,
    handleNextRound,
    getQuestionCount,
    getAnswerKey,
    handleScore,
    handleNext,
    handlePrevious,
    handleSubmit,
    determineTrack,
  };
}

import { useLayoutEffect, useRef, useState } from 'react';
import { assessmentAPI } from '../api/services';
import type { Question, Answer, AssessmentResult, AssessmentMode } from '../types';
import {
  HiAcademicCap, HiCheckCircle, HiArrowLeft, HiArrowRight, HiLightBulb, HiSparkles,
  HiBookOpen, HiTranslate, HiCalculator, HiChartBar, HiGlobeAlt, HiBeaker,
} from 'react-icons/hi';

// 文理分組與系所名稱對照由後端統一處理（backend/app/services/department_names.py）：
// - 每張題卡帶 tracks（'liberal' / 'science'），高二依此分組
// - 高三 filter-by-subjects 直接回傳題庫中的系所名稱
type Track = 'liberal' | 'science';

export default function AssessmentPage() {
  const pageTopRef = useRef<HTMLDivElement | null>(null);
  const questionCardRef = useRef<HTMLDivElement | null>(null);
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

  // 換題時滾回頂端
  useLayoutEffect(() => {
    const scrollQuestionCardToTop = () => {
      const card = questionCardRef.current;
      const page = pageTopRef.current;
      const anchor = card ?? page;
      if (!anchor) return;

      const nav = document.querySelector('nav');
      const navHeight = nav instanceof HTMLElement ? nav.offsetHeight : 0;
      const topOffset = navHeight + 12;

      let parent = anchor.parentElement;
      while (parent) {
        const style = window.getComputedStyle(parent);
        const isScrollable = /(auto|scroll)/.test(style.overflowY) && parent.scrollHeight > parent.clientHeight;
        if (isScrollable) {
          const parentRect = parent.getBoundingClientRect();
          const anchorRect = anchor.getBoundingClientRect();
          const delta = anchorRect.top - parentRect.top;
          parent.scrollTop += delta - 12;
          break;
        }
        parent = parent.parentElement;
      }

      const rect = anchor.getBoundingClientRect();
      const absoluteTop = window.scrollY + rect.top - topOffset;
      window.scrollTo({ top: Math.max(absoluteTop, 0) });
    };

    const rafId = window.requestAnimationFrame(scrollQuestionCardToTop);
    const timeoutId = window.setTimeout(scrollQuestionCardToTop, 60);
    return () => {
      window.cancelAnimationFrame(rafId);
      window.clearTimeout(timeoutId);
    };
  }, [currentIndex]);

  const modes = [
    {
      id: 'grade1' as AssessmentMode,
      title: '高一模式',
      description: '文組 vs 理組分類',
      subtitle: '初步了解自己適合的學習方向',
      icon: '1',
    },
    {
      id: 'grade2' as AssessmentMode,
      title: '高二模式',
      description: '細分科系探索',
      subtitle: '深入探索各個科系的研究領域',
      icon: '2',
    },
    {
      id: 'grade3' as AssessmentMode,
      title: '高三模式',
      description: '結合學測分數',
      subtitle: '根據實際成績找到最適合的科系',
      icon: '3',
    },
  ];

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
        alert('依你選擇的學測科目，目前沒有可報名的科系題卡，請調整科目後再試');
        setStarted(false);
        return;
      }
      setQuestions(data);
      setCurrentIndex(0);
      setAnswers(new Map());
      setResult(null);
    } catch (error) {
      console.error('載入題目失敗:', error);
      alert('載入題目失敗，請稍後再試');
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
      alert('提交失敗，請稍後再試');
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

  // 選擇模式畫面
  if (!started) {
    return (
      <div ref={pageTopRef} className="page-container py-8">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-primary-900 mb-2">科系興趣量表</h1>
          <p className="text-sm text-gray-600">
            選擇適合你的測評模式，開始探索未來方向
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12 max-w-5xl mx-auto">
          {modes.map((m) => (
            <button
              key={m.id}
              onClick={() => {
                setMode(m.id);
                setTrackType(null); // 切換模式時重置文理選擇
                setSelectedSubjects([]); // 切換模式時重置學測科目選擇
              }}
              className={`card-interactive p-8 text-left transition-all ${
                mode === m.id
                  ? 'ring-2 ring-primary-600 bg-primary-50'
                  : ''
              }`}
            >
              <div className="flex items-center justify-center w-12 h-12 bg-primary-100 text-primary-700 rounded-lg mb-4 text-2xl font-bold">
                {m.icon}
              </div>
              <h3 className="text-xl font-bold text-primary-900 mb-2">
                {m.title}
              </h3>
              <p className="text-primary-700 font-medium mb-2">
                {m.description}
              </p>
              <p className="text-gray-600 text-sm">{m.subtitle}</p>
            </button>
          ))}
        </div>

        {/* 高二模式：文理分組選擇 */}
        {mode === 'grade2' && (
          <div className="w-full max-w-5xl mx-auto mb-12">
            <div className="card p-8">
              <h3 className="text-lg font-bold text-primary-900 mb-4">請選擇你的類組</h3>
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => setTrackType('liberal')}
                  className={`p-6 rounded-lg border-2 transition-all ${
                    trackType === 'liberal'
                      ? 'border-primary-600 bg-primary-50'
                      : 'border-gray-200 hover:border-primary-300'
                  }`}
                >
                  <div className="text-center">
                    <HiBookOpen className={`w-8 h-8 mx-auto mb-2 ${trackType === 'liberal' ? 'text-primary-600' : 'text-gray-400'}`} />
                    <h4 className="text-xl font-bold text-primary-900 mb-1">文組</h4>
                    <p className="text-sm text-gray-600">文學、管理、客家</p>
                  </div>
                </button>
                <button
                  onClick={() => setTrackType('science')}
                  className={`p-6 rounded-lg border-2 transition-all ${
                    trackType === 'science'
                      ? 'border-primary-600 bg-primary-50'
                      : 'border-gray-200 hover:border-primary-300'
                  }`}
                >
                  <div className="text-center">
                    <HiBeaker className={`w-8 h-8 mx-auto mb-2 ${trackType === 'science' ? 'text-primary-600' : 'text-gray-400'}`} />
                    <h4 className="text-xl font-bold text-primary-900 mb-1">理組</h4>
                    <p className="text-sm text-gray-600">理學、工程、資訊</p>
                  </div>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 高三模式：學測科目選擇 */}
        {mode === 'grade3' && (
          <div className="w-full max-w-5xl mx-auto mb-12">
            <div className="card p-8">
              <h3 className="text-lg font-bold text-primary-900 mb-4">請選擇你的學測科目</h3>
              <p className="text-sm text-gray-600 mb-4">選擇你想要採計的學測科目，系統會篩選出符合的科系</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {[
                  { id: 'chinese',  label: '國文',  Icon: HiBookOpen },
                  { id: 'english',  label: '英文',  Icon: HiTranslate },
                  { id: 'math_a',   label: '數學A', Icon: HiCalculator },
                  { id: 'math_b',   label: '數學B', Icon: HiChartBar },
                  { id: 'social',   label: '社會',  Icon: HiGlobeAlt },
                  { id: 'science',  label: '自然',  Icon: HiBeaker },
                ].map(({ id, label, Icon }) => {
                  const selected = selectedSubjects.includes(id);
                  return (
                    <button
                      key={id}
                      onClick={() => {
                        setSelectedSubjects(prev =>
                          prev.includes(id)
                            ? prev.filter(s => s !== id)
                            : [...prev, id]
                        );
                      }}
                      className={`p-4 rounded-lg border-2 transition-all ${
                        selected
                          ? 'border-primary-600 bg-primary-50'
                          : 'border-gray-200 hover:border-primary-300'
                      }`}
                    >
                      <div className="text-center">
                        <Icon className={`w-6 h-6 mx-auto mb-1 ${selected ? 'text-primary-600' : 'text-gray-400'}`} />
                        <div className="text-sm font-semibold text-primary-900">{label}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
              {selectedSubjects.length > 0 && (
                <div className="mt-4 p-3 bg-primary-50 rounded-lg">
                  <p className="text-sm text-primary-800">
                    已選擇 <span className="font-bold">{selectedSubjects.length}</span> 個科目
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="text-center mb-12">
          <button
            onClick={handleStart}
            disabled={(mode === 'grade2' && !trackType) || (mode === 'grade3' && selectedSubjects.length === 0) || loading}
            className="btn-primary text-lg px-10 py-4 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '載入中...' : '開始測評'}
          </button>
          {mode === 'grade2' && !trackType && (
            <p className="text-sm text-gray-500 mt-2">請先選擇你的類組</p>
          )}
          {mode === 'grade3' && selectedSubjects.length === 0 && (
            <p className="text-sm text-gray-500 mt-2">請至少選擇一個學測科目</p>
          )}
        </div>

        <div className="card p-8 w-full max-w-5xl mx-auto">
          <div className="flex items-start space-x-3 mb-4">
            <HiLightBulb className="w-6 h-6 text-primary-600 flex-shrink-0 mt-1" />
            <div>
              <h4 className="text-lg font-bold text-primary-900 mb-3">測評說明</h4>
              <ul className="space-y-2 text-gray-600">
                <li className="flex items-start">
                  <span className="text-primary-600 mr-2">•</span>
                  <span>每個大學部學系 1 張研究題卡，每張 3 題，每題評分 1-5 分</span>
                </li>
                <li className="flex items-start">
                  <span className="text-primary-600 mr-2">•</span>
                  <span>
                    {mode === 'grade1' && '高一：文、理組各 5 個學系，共 10 張（30 題），約 10 分鐘'}
                    {mode === 'grade2' && '高二：文組 8 個學系全出（24 題，約 8 分鐘）；理組 16 個學系全出（48 題，約 15 分鐘）'}
                    {mode === 'grade3' && '高三：只出你可報名的學系，每輪最多 16 張（約 15 分鐘）；沒出到的學系可在結果頁再測一輪'}
                  </span>
                </li>
                <li className="flex items-start">
                  <span className="text-primary-600 mr-2">•</span>
                  <span>題目基於真實的大專生研究計畫，研究所的研究併入所屬學系；每次測驗會輪替不同的研究題卡</span>
                </li>
                <li className="flex items-start">
                  <span className="text-primary-600 mr-2">•</span>
                  <span>完成後將獲得詳細的科系推薦報告</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 載入中
  if (loading && questions.length === 0) {
    return (
      <div ref={pageTopRef} className="page-container py-8 text-center">
        <div className="card p-16 max-w-md mx-auto">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-primary-700 mx-auto mb-4"></div>
          <p className="text-gray-600">載入題目中...</p>
        </div>
      </div>
    );
  }

  // 顯示結果
  if (result) {
    const track = mode === 'grade1' ? determineTrack() : trackType;
    const answeredDepts = new Set([...prevDepts, ...questions.map(q => q.department)]);
    const uncovered = mode === 'grade3' ? eligibleUnits.filter(d => !answeredDepts.has(d)) : [];
    const colleges = result.colleges ?? [];

    return (
      <div ref={pageTopRef} className="page-container py-8">
        {/* 簡潔的標題 */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 rounded-full mb-4">
            <HiCheckCircle className="w-10 h-10 text-green-600" />
          </div>
          <h1 className="text-3xl font-bold text-primary-900">測評完成</h1>
        </div>

        {/* 高一模式：顯示文理分組結果 */}
        {mode === 'grade1' && track && (
          <div className="card p-6 mb-8 max-w-3xl mx-auto bg-primary-50 border-primary-200">
            <div className="flex items-center justify-center space-x-3">
              <HiSparkles className="w-6 h-6 text-primary-700" />
              <p className="text-lg">
                <span className="text-gray-700">根據測評結果，你較適合</span>
                <span className="text-2xl font-bold text-primary-700 mx-2">
                  {track === 'liberal' ? '文組' : '理組'}
                </span>
                <span className="text-gray-700">的學習方向</span>
              </p>
            </div>
            {result.trackScores && (
              <p className="text-sm text-gray-600 text-center mt-2">
                文組題卡平均 {(result.trackScores.liberal ?? 0).toFixed(1)} 分・理組題卡平均 {(result.trackScores.science ?? 0).toFixed(1)} 分（滿分 5）
              </p>
            )}
          </div>
        )}

        {/* 推薦科系 */}
        <div className="max-w-5xl mx-auto">
          <h2 className="text-xl font-bold text-primary-900 mb-6">為你推薦的科系</h2>

          {/* Top 3 特別顯示 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {result.departments.slice(0, 3).map((dept, index) => (
              <div
                key={dept.name}
                className="card p-6 text-center hover:shadow-medium transition-shadow"
              >
                <div className={`inline-flex items-center justify-center w-12 h-12 rounded-full mb-3 ${
                  index === 0 ? 'bg-amber-100' :
                  index === 1 ? 'bg-gray-200' : 'bg-orange-100'
                }`}>
                  <span className={`text-2xl font-bold ${
                    index === 0 ? 'text-amber-600' :
                    index === 1 ? 'text-gray-600' : 'text-orange-600'
                  }`}>{index + 1}</span>
                </div>
                <h3 className="text-lg font-bold text-primary-900 mb-1">{dept.name}</h3>
                <p className="text-sm text-gray-600 mb-3">{dept.college}</p>
                <div className="text-3xl font-bold text-primary-700">
                  {dept.score.toFixed(1)}
                </div>
                <div className="text-xs text-gray-500">興趣平均分（滿分 5）</div>
              </div>
            ))}
          </div>

          {/* 其他推薦 */}
          <div className="card p-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">其他推薦科系</h3>
            <div className="space-y-2">
              {result.departments.slice(3, 10).map((dept, index) => (
                <div
                  key={dept.name}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <div className="flex items-center space-x-3">
                    <span className="text-sm font-semibold text-gray-500 w-6">{index + 4}</span>
                    <div>
                      <h4 className="font-semibold text-primary-900">{dept.name}</h4>
                      <p className="text-xs text-gray-600">{dept.college}</p>
                    </div>
                  </div>
                  <div className="text-lg font-bold text-primary-700">
                    {dept.score.toFixed(1)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 高三：這一輪沒出到的可報名學系 */}
        {uncovered.length > 0 && (
          <div className="card p-6 mt-8 max-w-5xl mx-auto border-amber-200 bg-amber-50">
            <h2 className="text-lg font-bold text-primary-900 mb-2">
              還有 {uncovered.length} 個你可報名的學系沒有出到
            </h2>
            <p className="text-sm text-gray-600 mb-3">{uncovered.join('、')}</p>
            <button onClick={handleNextRound} className="btn-primary">
              再測一輪（{uncovered.length} 張題卡，約 {uncovered.length} 分鐘）
            </button>
            <p className="text-xs text-gray-500 mt-2">這一輪的作答會保留，完成後一起排名</p>
          </div>
        )}

        {/* 學院排名 */}
        {colleges.length > 0 && (
          <div className="card p-8 mt-8 max-w-5xl mx-auto">
            <h2 className="text-lg font-bold text-primary-900 mb-2">學院排名</h2>
            <p className="text-xs text-gray-500 mb-6">該學院所有研究題卡的平均分（滿分 5），括號內為作答的題卡數</p>
            <div className="space-y-3">
              {colleges.map((college, index) => (
                <div key={college.name} className="flex items-center gap-3">
                  <span className="text-sm font-semibold text-gray-500 w-6">{index + 1}</span>
                  <span className="text-sm font-semibold text-primary-900 w-28 shrink-0">{college.name}</span>
                  <div className="flex-1 h-2.5 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary-600 rounded-full"
                      style={{ width: `${(college.score / 5) * 100}%` }}
                    ></div>
                  </div>
                  <span className="text-sm font-bold text-primary-700 w-10 text-right">{college.score.toFixed(1)}</span>
                  <span className="text-xs text-gray-500 w-12">（{college.count} 張）</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 興趣標籤 */}
        <div className="card p-8 mt-8 max-w-5xl mx-auto">
          <h2 className="text-lg font-bold text-primary-900 mb-2">你的興趣標籤</h2>
          <p className="text-xs text-gray-500 mb-6">分數為帶有該標籤的研究題卡平均分（滿分 5）</p>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            {result.tagScores.slice(0, 12).map((tag) => (
              <div
                key={tag.tag}
                className="p-3 bg-primary-50 rounded-lg text-center hover:bg-primary-100 transition-colors"
              >
                <div className="text-2xl font-bold text-primary-700 mb-1">
                  {tag.score.toFixed(1)}
                </div>
                <div className="text-xs text-gray-700 font-medium">{tag.tag}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="text-center mt-8">
          <button
            onClick={() => {
              setStarted(false);
              setResult(null);
              setTrackType(null);
            }}
            className="btn-secondary"
          >
            重新測評
          </button>
        </div>
      </div>
    );
  }

  // 答題畫面
  const current = questions[currentIndex];

  if (!current) {
    return (
      <div ref={pageTopRef} className="page-container py-8 text-center">
        <div className="card p-16 max-w-md mx-auto">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-primary-700 mx-auto mb-4"></div>
          <p className="text-gray-600">載入中...</p>
        </div>
      </div>
    );
  }

  const currentPrompts = current.questions?.length
    ? current.questions
    : ['這個研究主題讓你感興趣嗎？'];
  const currentScores = currentPrompts.map((_, index) => answers.get(getAnswerKey(current.id, index)) || 0);
  const currentComplete = currentScores.every((score) => score > 0);
  const progress = ((currentIndex + 1) / questions.length) * 100;
  const answeredCount = answers.size;
  const totalAnswerCount = questions.reduce((sum, question) => sum + getQuestionCount(question), 0);
  const canSubmit = answeredCount === totalAnswerCount;

  // 計算有多少個不同的科系
  const uniqueDepartments = new Set(questions.map(q => q.department));
  const departmentCount = uniqueDepartments.size;

  return (
    <div ref={pageTopRef} className="page-container py-8">
      {/* 題目卡片 */}
      <div ref={questionCardRef} className="card p-8 mb-6 max-w-4xl mx-auto">
        <div className="flex items-start space-x-3 mb-6">
          <HiAcademicCap className="w-6 h-6 text-primary-600 flex-shrink-0 mt-1" />
          <h2 className="text-2xl font-bold text-primary-900">{current.title}</h2>
        </div>

        <div className="space-y-6 mb-8">
          {current.intro ? (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">主題導讀</h3>
              <p className="text-gray-600 leading-relaxed">{current.intro}</p>
            </div>
          ) : (
            <>
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">研究動機與問題</h3>
                <p className="text-gray-600 leading-relaxed">{current.motivation}</p>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">研究方法</h3>
                <p className="text-gray-600 leading-relaxed">{current.method}</p>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">研究結果</h3>
                <p className="text-gray-600 leading-relaxed">{current.result}</p>
              </div>
            </>
          )}

          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">領域標籤</h3>
            <div className="flex flex-wrap gap-2">
              {current.tags.map((tag) => (
                <span
                  key={tag}
                  className="badge badge-primary"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* 評分區 */}
        <div className="border-t border-gray-200 pt-6">
          <h3 className="text-lg font-bold text-primary-900 mb-4">
            請分別評分你對這些問題的興趣
          </h3>
          <div className="space-y-6">
            {currentPrompts.map((prompt, questionIndex) => {
              const selectedScore = currentScores[questionIndex];
              return (
                <div key={`${current.id}-score-${questionIndex}`} className="rounded-lg bg-gray-50 p-4">
                  <div className="mb-3 flex gap-3 text-gray-700 leading-relaxed">
                    <span className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-semibold text-primary-700">
                      {questionIndex + 1}
                    </span>
                    <p>{prompt}</p>
                  </div>
                  <div className="mb-2 flex justify-between text-xs text-gray-500">
                    <span>1 分 - 完全不感興趣</span>
                    <span>5 分 - 非常感興趣</span>
                  </div>
                  <div className="grid grid-cols-5 gap-3">
                    {[1, 2, 3, 4, 5].map((score) => (
                      <button
                        key={score}
                        onClick={() => handleScore(score, questionIndex)}
                        className={`py-4 rounded-lg font-bold text-lg transition-all ${
                          selectedScore === score
                            ? 'bg-primary-700 text-white ring-2 ring-primary-600 ring-offset-2 scale-105'
                            : 'bg-white text-gray-700 hover:bg-gray-100 border border-gray-200'
                        }`}
                      >
                        {score}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 導航按鈕 */}
      <div className="flex justify-between items-center max-w-4xl mx-auto">
        <button
          onClick={handlePrevious}
          disabled={currentIndex === 0}
          className="btn-secondary disabled:opacity-50"
        >
          <HiArrowLeft className="w-5 h-5 mr-2" />
          上一題
        </button>

        {currentIndex < questions.length - 1 ? (
          <button
            onClick={handleNext}
            disabled={!currentComplete}
            className="btn-primary disabled:opacity-50"
          >
            下一題
            <HiArrowRight className="w-5 h-5 ml-2" />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!canSubmit || loading}
            className="btn-primary disabled:opacity-50"
          >
            {loading ? '提交中...' : '完成測評'}
          </button>
        )}
      </div>

      {/* 進度條 */}
      <div className="mt-4 max-w-4xl mx-auto">
        <div className="flex justify-between items-center text-xs text-gray-500 mb-1.5">
          <div className="flex items-center gap-3">
            <span>第 {currentIndex + 1} / {questions.length} 題</span>
            <span className="text-primary-600">涵蓋 {departmentCount} 個科系</span>
          </div>
          <span>已完成 {answeredCount} / {totalAnswerCount} 題</span>
        </div>
        <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-primary-700 transition-all duration-300"
            style={{ width: `${progress}%` }}
          ></div>
        </div>
      </div>

      {/* 提示訊息 */}
      {!currentComplete && (
        <p className="text-center text-gray-500 mt-4 text-sm">
          請完成這張卡片的所有評分後再繼續
        </p>
      )}
      {!canSubmit && currentIndex === questions.length - 1 && (
        <p className="text-center text-amber-600 mt-4 text-sm">
          還有 {totalAnswerCount - answeredCount} 題未完成，請完成所有題目後提交
        </p>
      )}
    </div>
  );
}

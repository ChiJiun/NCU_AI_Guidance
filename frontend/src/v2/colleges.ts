/** 新版畫面的學院代表色（皆為深色階，白底與紙色底上的文字對比都在 4.5:1 以上）。 */
const COLLEGE_HEX: Record<string, string> = {
  文學院: '#6D28D9',
  理學院: '#0369A1',
  工學院: '#C2410C',
  管理學院: '#047857',
  資訊電機學院: '#4338CA',
  地球科學學院: '#0F766E',
  客家學院: '#BE185D',
  生醫理工學院: '#BE123C',
  永續與綠能科技研究學院: '#4D7C0F',
  永續與綠能學院: '#4D7C0F',
};

const DEFAULT_HEX = '#475569';

/** 學院名稱 → 代表色。定義在模組層級，參考穩定，可以直接當 hook 的相依。 */
export const collegeHex = (collegeName: string): string => COLLEGE_HEX[collegeName] ?? DEFAULT_HEX;

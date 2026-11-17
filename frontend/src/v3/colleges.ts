/**
 * v3 的學院代表色：沿用舊版（v1 CoursesPage 的 COLLEGE_CONFIG）的色系，
 * 取該色系的 700 色階（舊版學院 badge 文字用的深度），白底上的文字對比都在 4.5:1 以上。
 */
const COLLEGE_HEX: Record<string, string> = {
  文學院: '#6D28D9', // violet-700
  理學院: '#0E7490', // cyan-700
  工學院: '#C2410C', // orange-700
  管理學院: '#047857', // emerald-700
  資訊電機學院: '#4338CA', // indigo-700
  地球科學學院: '#0F766E', // teal-700
  客家學院: '#BE123C', // rose-700
  生醫理工學院: '#B91C1C', // red-700
  永續與綠能科技研究學院: '#4D7C0F', // lime-700
  永續與綠能學院: '#4D7C0F',
};

const DEFAULT_HEX = '#475569'; // slate-600

/** 學院名稱 → 代表色。定義在模組層級，參考穩定，可以直接當 hook 的相依。 */
export const collegeHexV3 = (collegeName: string): string => COLLEGE_HEX[collegeName] ?? DEFAULT_HEX;

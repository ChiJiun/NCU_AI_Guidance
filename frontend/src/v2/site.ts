import { createContext, useContext } from 'react';
import { collegeHex } from './colleges';
import { v2Link } from './paths';

/**
 * v2 的頁面元件也被 v3（/v3）重用，兩版只差在站內連結與學院配色。
 * 頁面透過 useSite() 取得這兩個函式；沒有外層 Provider 時就是 v2 自己的設定，v2 畫面不受影響。
 */
export interface SiteConfig {
  /** 舊版路徑 → 這一版的站內連結（這一版沒有的頁面連回舊版） */
  link: (legacyPathname: string) => string;
  /** 學院名稱 → 代表色。必須是參考穩定的函式（會當成 hook 的相依） */
  collegeHex: (collegeName: string) => string;
}

export const V2_SITE: SiteConfig = { link: v2Link, collegeHex };

export const SiteContext = createContext<SiteConfig>(V2_SITE);

export const useSite = (): SiteConfig => useContext(SiteContext);

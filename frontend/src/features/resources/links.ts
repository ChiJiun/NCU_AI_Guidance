/** 資源連結頁的連結資料（逐字搬自舊版 ResourcesPage，新舊版共用）。 */

export interface ResourceLink {
  title: string;
  description: string;
  href: string;
}

export const scoreResources: ResourceLink[] = [
  {
    title: '114大學交叉查榜｜www.com.tw',
    description: '查詢大學申請、繁星、分科與統測榜單，也可查看各系組錄取分數與交叉查榜資訊。',
    href: 'https://www.com.tw/cross/',
  },
  {
    title: '大學甄選入學委員會',
    description: '查詢大學申請入學與繁星推薦的官方招生簡章、重要時程、校系分則與錄取公告。',
    href: 'https://www.uac.edu.tw/',
  },
  {
    title: '1111落點分析',
    description: '輸入成績後進行校系落點分析，搭配學群、志願與升學建議評估可能錄取範圍。',
    href: 'https://exam-match.1111.com.tw/',
  },
];

export const studyResources: ResourceLink[] = [
  {
    title: 'ColleGo!',
    description: '探索大學學群、學類、校系與高中學習準備方向，適合用來認識科系與規劃學習路徑。',
    href: 'https://collego.edu.tw/',
  },
  {
    title: 'IOH 開放個人經驗平台',
    description: '透過學長姐與講者的求學、科系、職涯經驗分享，了解不同校系的實際學習樣貌。',
    href: 'https://ioh.tw/',
  },
  {
    title: '大學問',
    description: '查詢大學校系、學群分類、入學管道與升學新聞，適合快速比較不同學校與科系資訊。',
    href: 'https://www.unews.com.tw/',
  },
];

export const departmentGroups: { college: string; links: [string, string][] }[] = [
  {
    college: '文學院',
    links: [
      ['文學院學士班', 'https://ipla.ncu.edu.tw/'],
      ['中國文學系', 'https://www.chinese.ncu.edu.tw/'],
      ['英美語文學系', 'https://english.ncu.edu.tw/'],
      ['法國語文學系', 'https://french.ncu.edu.tw/'],
    ],
  },
  {
    college: '理學院',
    links: [
      ['理學院學士班', 'https://www.science.ncu.edu.tw/'],
      ['化學學系', 'https://www.chem.ncu.edu.tw/'],
      ['物理學系', 'https://www.phy.ncu.edu.tw/'],
      ['數學系', 'https://w2.math.ncu.edu.tw/'],
      ['光電科學與工程學系', 'https://www.dop.ncu.edu.tw/'],
    ],
  },
  {
    college: '工學院',
    links: [
      ['工學院學士班', 'https://ipe.ec.ncu.edu.tw/'],
      ['土木工程學系', 'https://www.cv.ncu.edu.tw/'],
      ['化學工程與材料工程學系', 'https://www.cme.ncu.edu.tw/'],
      ['機械工程學系', 'https://www.me.ncu.edu.tw/'],
    ],
  },
  {
    college: '管理學院',
    links: [
      ['經濟學系', 'https://ec.mgt.ncu.edu.tw/'],
      ['企業管理學系', 'https://ba.mgt.ncu.edu.tw/'],
      ['財務金融學系', 'https://fm.mgt.ncu.edu.tw/'],
      ['資訊管理學系', 'https://im.mgt.ncu.edu.tw/'],
    ],
  },
  {
    college: '資訊電機學院',
    links: [
      ['資訊電機學院學士班', 'https://www.ipeecs.ncu.edu.tw/'],
      ['電機工程學系', 'https://www2.ee.ncu.edu.tw/'],
      ['資訊工程學系', 'https://www.csie.ncu.edu.tw/'],
      ['通訊工程學系', 'https://www.ce.ncu.edu.tw/'],
    ],
  },
  {
    college: '地球科學學院',
    links: [
      ['地球科學學院學士班', 'https://escollege.ncu.edu.tw/'],
      ['地球科學學系', 'https://www.gep.ncu.edu.tw/'],
      ['大氣科學學系', 'https://www.atm.ncu.edu.tw/'],
      ['太空科學與工程學系', 'https://www.ss.ncu.edu.tw/'],
    ],
  },
  {
    college: '客家學院',
    links: [['客家語文暨社會科學學系', 'https://hakka.ncu.edu.tw/']],
  },
  {
    college: '生醫理工學院',
    links: [
      ['生命科學系', 'https://nculs.in.ncu.edu.tw/'],
      ['生醫科學與工程學系', 'https://ncu.edu.tw/dbse/tw/index.php'],
    ],
  },
];

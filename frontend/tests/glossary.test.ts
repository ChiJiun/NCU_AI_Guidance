// 執行：npm run test:unit（Node 內建測試，不需額外套件）
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createMatcher, injectGlossary } from '../src/components/glossary.ts';

const matcher = createMatcher({
  '反向傳播': '從輸出誤差往回調整權重的方法',
  '音韻': '聲音如何組合的規律',
  '音韻學': '研究語言聲音規律的學科',
  '神經網路': '分層運算的模型',
  '神經網絡': '分層運算的模型',
  'SVM': '畫出最佳分界線的分類模型',
});

test('標出術語並回傳命中清單', () => {
  const { text, hits } = injectGlossary('反向傳播是訓練的核心。', matcher);
  assert.equal(text, '<dfn data-gi="0">反向傳播</dfn>是訓練的核心。');
  assert.deepEqual(hits, [{ surface: '反向傳播', gloss: '從輸出誤差往回調整權重的方法' }]);
});

test('同一個詞只標第一次出現', () => {
  const { text, hits } = injectGlossary('反向傳播很重要，反向傳播也很難。', matcher);
  assert.equal(hits.length, 1);
  assert.equal(text.match(/<dfn/g)?.length, 1);
});

test('別名視為同一個詞，只標一次', () => {
  const { hits } = injectGlossary('神經網絡與神經網路。', matcher);
  assert.equal(hits.length, 1);
  assert.equal(hits[0].surface, '神經網絡');
});

test('長詞優先，不被短詞吃掉', () => {
  const { hits } = injectGlossary('音韻學是一門學科。', matcher);
  assert.deepEqual(hits.map((h) => h.surface), ['音韻學']);
});

test('課名標籤與課名按鈕裡的字不標', () => {
  const a = injectGlossary('推薦<course>反向傳播實作（資訊工程學系）</course>。', matcher);
  assert.equal(a.hits.length, 0);
  const b = injectGlossary('推薦<mark data-cid="0">反向傳播實作</mark>。', matcher);
  assert.equal(b.hits.length, 0);
});

test('程式碼、連結、網址裡的字不標', () => {
  for (const t of ['`反向傳播`', '```\n反向傳播\n```', '[反向傳播](https://x.y)', 'https://example.com/反向傳播']) {
    assert.equal(injectGlossary(t, matcher).hits.length, 0, t);
  }
});

test('串流中尚未閉合的程式碼區塊不標', () => {
  assert.equal(injectGlossary('說明如下\n```python\n# 反向傳播', matcher).hits.length, 0);
});

test('保護區段前後的文字仍會標', () => {
  const { hits } = injectGlossary('先看 `x` 再談反向傳播。', matcher);
  assert.equal(hits.length, 1);
});

test('英文縮寫不會標在較長的英數字串中間', () => {
  assert.equal(injectGlossary('MSVMX 與 SVM2', matcher).hits.length, 0);
  assert.equal(injectGlossary('使用 SVM 分類。', matcher).hits.length, 1);
});

test('空詞庫或空文字原樣回傳', () => {
  assert.equal(injectGlossary('任何文字', createMatcher({})).text, '任何文字');
  assert.equal(injectGlossary('', matcher).text, '');
});

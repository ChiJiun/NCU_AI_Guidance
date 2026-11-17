import { useEffect, useState } from 'react';
import { MeshGradient, Shader, getWebGPUSupport } from 'shaders/react';

/**
 * 首頁 hero 的動態背景（WebGPU，shaders 套件）：把舊版首頁的粉彩漸層底（index.css 的 bg-theme-1）做成緩慢流動的網格漸層。
 * - 整個模組由 HomeV3 以 lazy 載入，只在「不要求減少動態、螢幕 ≥ 768px、瀏覽器有 navigator.gpu」時才會掛載。
 * - 這裡再確認一次 WebGPU 真的可用；不可用或初始化失敗就不渲染，底下的 CSS 靜態漸層維持原樣。
 * - 畫面就緒後才淡入（.is-ready），避免先閃出空白畫布。
 * - disableTelemetry：不送匿名使用統計。
 */
const STOPS = [
  { color: '#fbfdff', position: 0 },
  { color: '#c4f4e9', position: 0.25 },
  { color: '#eef5ff', position: 0.5 },
  { color: '#fcf1b6', position: 0.75 },
  { color: '#dbeafe', position: 1 },
];

export default function HeroGradient() {
  const [supported, setSupported] = useState(false);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getWebGPUSupport()
      .then((info) => {
        if (!cancelled) setSupported(info.supported);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!supported || failed) return null;

  return (
    <Shader
      disableTelemetry
      className={`v3-hero-canvas ${ready ? 'is-ready' : ''}`}
      onReady={() => setReady(true)}
      onUnavailable={() => setFailed(true)}
    >
      <MeshGradient stops={STOPS} count={5} smoothness={3} swirl={0.15} drift={0.35} speed={0.25} seed={7} />
    </Shader>
  );
}

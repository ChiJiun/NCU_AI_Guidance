import { useEffect, useState } from 'react';
import { Circle, ContourLines, FlowingGradient, Shader, SolidColor, getWebGPUSupport } from 'shaders/react';

/**
 * 首頁 hero 的動態等高線（WebGPU，shaders 套件）。
 * - 整個模組由 HomeV2 以 lazy 載入，只在「不要求減少動態、螢幕 ≥ 768px、瀏覽器有 navigator.gpu」時才會掛載。
 * - 這裡再確認一次 WebGPU 真的可用；不可用或初始化失敗就不渲染，底下的 CSS 靜態等高線維持原樣。
 * - 畫面就緒後才淡入（.is-ready），避免先閃出空白畫布。
 * - disableTelemetry：不送匿名使用統計。
 */
export default function HeroShader() {
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
      className={`v2-hero-canvas ${ready ? 'is-ready' : ''}`}
      onReady={() => setReady(true)}
      onUnavailable={() => setFailed(true)}
    >
      <SolidColor color="#f5f2ea" />
      {/* 只讓右側顯現線條，左側留給標題 */}
      <Circle id="heroMask" visible={false} color="#ffffff" radius={2} softness={1} center={{ x: 1, y: 0.5 }} />
      <ContourLines
        maskSource="heroMask"
        levels={14}
        lineWidth={1}
        colorMode="custom"
        lineColor="#15202b"
        backgroundColor="transparent"
        opacity={0.35}
      >
        <FlowingGradient colorA="#000000" colorB="#ffffff" colorC="#7a7a7a" colorD="#3a3a3a" speed={0.25} />
      </ContourLines>
    </Shader>
  );
}

import { Component, type ErrorInfo, type ReactNode } from 'react';

type Props = {
  /** 子元件（通常是 lazy 載入的 chunk）丟出錯誤時改顯示這個 */
  fallback: ReactNode;
  children: ReactNode;
};

type State = { failed: boolean };

/**
 * 包住 lazy 載入的區塊：chunk 下載失敗（例如重新部署後舊 hash 的檔案已不存在）
 * 或渲染時丟出錯誤，只讓這一塊改顯示 fallback，不要讓整個 app 變成白畫面。
 */
export default class LoadErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[LoadErrorBoundary]', error, info.componentStack);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

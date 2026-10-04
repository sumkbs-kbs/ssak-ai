import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { sanitizeLegacyBrowserSettings } from './utils/browserSettings';
import './styles/index.css';
/*
 * CR-09(F05): 코드 하이라이트 테마를 로컬 번들에서 가져온다.
 * 이전에는 index.html이 CDN(highlight.js 11.9.0)에서 불러왔고, 설치된 하이라이터
 * (lowlight → highlight.js 11.11.2)와 버전도 어긋났다. 지금은 같은 패키지의 CSS를
 * 빌드에 포함해 오프라인에서도 코드 블록이 색을 잃지 않는다.
 */
import 'highlight.js/styles/tokyo-night-dark.css';
import './styles/codex-workspace.css';

class DashboardBootstrapError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DashboardBootstrapError';
  }
}

const enableReactDevTools = import.meta.env.DEV
  && import.meta.env.VITE_ENABLE_REACT_DEVTOOLS === '1'
  && import.meta.env.VITE_DISABLE_REACT_DEVTOOLS !== '1';

if (enableReactDevTools) {
  void import('react-grab');
  void import('react-scan');
}

// ─── React Query Client ────────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 10_000,
      refetchOnWindowFocus: false,
    },
  },
});

/*
 * CR-09(F05): mermaid는 여기서 초기화하지 않는다. `src/utils/mermaidRuntime.ts`가
 * 다이어그램을 실제로 그릴 때 동적 import로 로드하고 그때 초기 설정을 적용한다.
 */

// ─── Global Error Handler ──────────────────────────────────────────
window.addEventListener('unhandledrejection', (event) => {
  console.error('[Unhandled Promise Rejection]', event.reason);
});

window.addEventListener('error', (event) => {
  if (event.target instanceof HTMLScriptElement) return;
  console.error('[Global Error]', event.error || event.message);
});

// ─── CR-05: legacy 브라우저 설정 정화 (원문 API 키 제거) ─────────────
// 예전 버전은 API 키를 localStorage에 원문 저장했다. 남아 있는 값을 첫 렌더
// 전에 정화한다(값은 읽지 않고 키 이름만 로그에 남긴다).
const legacyCleanup = sanitizeLegacyBrowserSettings();
if (legacyCleanup.removedKeys.length > 0) {
  console.info(
    `[Settings] 브라우저 저장소에서 비밀 설정 ${legacyCleanup.removedKeys.length}건을 제거했습니다.`,
  );
}

// ─── Render ────────────────────────────────────────────────────────
const rootElement = document.getElementById('root');
if (rootElement === null) throw new DashboardBootstrapError('Dashboard root element is missing.');

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);

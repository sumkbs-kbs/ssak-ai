/**
 * NotFoundPage — 없는 경로 안내 (CR-07)
 * =====================================
 * 발견 F03: `<Routes>`에 `path="*"`가 없어서 없는 경로가 **아무 안내 없이 빈 화면**이
 * 됐다. 이 화면은 요청한 경로를 보여주고 홈 복귀/뒤로가기를 제공한다.
 *
 * 안전 규칙:
 *  - 경로 원문은 React가 이스케이프해 그대로 렌더한다(HTML 삽입 없음).
 *  - 이 화면은 어떤 저장소도 지우지 않는다(대화·로컬 히스토리 보존).
 */

import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const NotFoundPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <div
      className="page-container not-found-page"
      data-testid="cr07-not-found"
      style={{ maxWidth: 640, margin: '0 auto', padding: '48px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}
    >
      <div className="hero-eyebrow">404</div>
      <h2 style={{ margin: 0 }}>페이지를 찾을 수 없습니다</h2>
      <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 14 }}>
        요청한 경로 <code data-testid="cr07-not-found-path">{location.pathname}</code>
        {' '}는 이 앱에 없습니다. 주소가 바뀌었거나 오래된 북마크일 수 있습니다.
      </p>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <button
          type="button"
          className="btn-primary"
          data-testid="cr07-not-found-home"
          onClick={() => navigate('/')}
        >
          ⌂ 채팅으로 돌아가기
        </button>
        <button
          type="button"
          className="btn-ghost"
          data-testid="cr07-not-found-back"
          onClick={() => navigate(-1)}
        >
          ← 뒤로
        </button>
      </div>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
        왼쪽 사이드바에서 원하는 화면을 선택할 수도 있습니다. 저장된 대화는 그대로 남아 있습니다.
      </p>
    </div>
  );
};

export default NotFoundPage;

/**
 * PinModal — PIN authentication modal for secure access
 */

import React, { useState, useRef, useEffect } from 'react';
import { useUiStore } from '../../stores/uiStore';
import { AccessPinLoginError, loginWithAccessPin } from '../../utils/accessPinCredential';

const loginFailureMessages: Record<AccessPinLoginError['kind'], string> = {
  invalid_pin: 'PIN 번호가 올바르지 않습니다.',
  locked: '인증 시도가 잠겼습니다. 잠시 후 다시 시도하세요.',
  rate_limited: '인증 요청이 너무 많습니다. 잠시 후 다시 시도하세요.',
  network: '서버에 연결할 수 없습니다. 서버 실행 상태와 네트워크를 확인하세요.',
  service_unavailable: '인증 서버를 사용할 수 없습니다. 잠시 후 다시 시도하세요.',
  invalid_response: '인증 응답을 확인할 수 없습니다. 잠시 후 다시 시도하세요.',
  request_failed: '인증을 완료할 수 없습니다. 잠시 후 다시 시도하세요.',
};

const PinModal: React.FC = () => {
  const visible = useUiStore(state => state.pinModalVisible);
  const setVisible = useUiStore(state => state.setPinModalVisible);
  const notice = useUiStore(state => state.pinModalNotice);
  const setNotice = useUiStore(state => state.setPinModalNotice);
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (visible && inputRef.current) {
      inputRef.current.focus();
    }
  }, [visible]);

  const handleSubmit = async () => {
    const trimmedPin = pin.trim();
    if (!trimmedPin) return;

    try {
      await loginWithAccessPin(trimmedPin);
      // 로그인에 성공하면 이유는 더 이상 유효하지 않다 — 다음 잠금이 낡은 문구를 물려받지 않게 지운다.
      setNotice('');
      setVisible(false);
    } catch (error) {
      setError(error instanceof AccessPinLoginError ? loginFailureMessages[error.kind] : loginFailureMessages.request_failed);
    }
  };

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="PIN 인증"
      style={{
        position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh',
        background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(10px)',
        zIndex: 99999, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        className="glass-panel"
        style={{ padding: 32, borderRadius: 16, textAlign: 'center', maxWidth: 300, width: '90%' }}
      >
        <h2 style={{ marginTop: 0 }}>🔒 시스템 잠금</h2>
        <p
          style={{ color: 'var(--text-secondary)', marginBottom: notice ? 12 : 24, fontSize: 'var(--text-md)', wordBreak: 'keep-all' }}
        >
          외부 접속 보안을 위해 PIN 번호를 입력하세요.
        </p>
        {notice && (
          <p
            role="status"
            data-testid="pin-modal-notice"
            style={{ color: 'var(--accent-color, #7c6aef)', marginBottom: 24, fontSize: 13, wordBreak: 'keep-all' }}
          >
            {notice}
          </p>
        )}
        <input
          ref={inputRef}
          type="password"
          value={pin}
          onChange={e => { setPin(e.target.value); setError(''); }}
          onKeyDown={e => e.key === 'Enter' && handleSubmit()}
          placeholder="PIN 입력"
          style={{
            width: '100%', padding: 12, borderRadius: 8, border: '1px solid var(--glass-border)',
            background: 'rgba(0,0,0,0.5)', color: '#fff', textAlign: 'center',
            fontSize: 20, letterSpacing: 4, boxSizing: 'border-box', marginBottom: 16,
          }}
          autoFocus
          aria-label="PIN 번호"
        />
        <button
          onClick={handleSubmit}
          className="glow-btn pin-unlock-button"
          style={{ width: '100%', padding: 12, borderRadius: 8, fontSize: 15, fontWeight: 'bold' }}
        >
          잠금 해제
        </button>
        {error && (
          <p style={{ color: '#ff6b6b', marginTop: 12, fontSize: 12 }} role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
};

export default PinModal;

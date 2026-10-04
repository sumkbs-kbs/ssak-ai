/**
 * SettingsPage — System Settings
 * ================================
 * Ported from Vanilla JS. API keys, model selection, search engine, cost control.
 */

import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { GlassPanel } from '../components/shared';
import { useThemeStore } from '../stores/themeStore';
import { useLocalHistoryStore } from '../stores/localHistoryStore';
import CacheStatsPanel from '../components/shared/CacheStatsPanel';
import McpHealthCachePanel from '../components/shared/McpHealthCachePanel';
import McpOAuthPanel from '../components/shared/McpOAuthPanel';
import ModelOperationsPanel from '../components/shared/ModelOperationsPanel';
import SessionDisclosurePanel from '../components/shared/SessionDisclosurePanel';
import SearchIntegrationPanel from '../components/Search/SearchIntegrationPanel';
import {
  changeAccessPin,
  deleteSettingsKeys,
  fetchLogLevels,
  fetchNetworkAccessInfo,
  fetchSettings,
  type NetworkAccessInfo,
  isAuthRequiredError,
  saveSettings,
  setLogLevel,
  setAllLogLevels,
  setDebugMode,
  type LogLevelInfo,
  type SettingsData,
} from '../api/client';
import { readBrowserSettings, writeBrowserSettings } from '../utils/browserSettings';
import { clearAccessCredential } from '../utils/accessPinCredential';
import { useUiStore } from '../stores/uiStore';

const PROVIDERS = [
  { key: 'OPENROUTER_API_KEY', label: 'OpenRouter', icon: '🌐', hint: 'openrouter.ai/keys' },
  { key: 'NVIDIA_API_KEY', label: 'NVIDIA NIM (무료)', icon: '🟢', hint: 'build.nvidia.com' },
  { key: 'OPENAI_API_KEY', label: 'OpenAI', icon: '🔵', hint: 'platform.openai.com/api-keys' },
  { key: 'GEMINI_API_KEY', label: 'Google Gemini', icon: '✨', hint: 'aistudio.google.com/apikey' },
  { key: 'ZAI_API_KEY', label: 'ZAI / Zhipu GLM', icon: '🧠', hint: 'open.bigmodel.cn' },
  { key: 'ANTHROPIC_API_KEY', label: 'Anthropic Claude', icon: '🟣', hint: 'console.anthropic.com' },
];

const THEME_COLORS = ['#7c6aef', '#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#a855f7', '#3b82f6', '#14b8a6'];

const FONT_SIZES = [12, 13, 14, 15, 16, 18, 20];

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * 후보 중 **제공된** 첫 값을 쓴다 (CR-06).
 *
 * `||`와 달리 `0`/`'0'`을 '값 없음'으로 보지 않는다 — 서버가 보고한 유효한
 * 0 예산·0 한도를 하드코딩 기본값으로 바꾸면 화면이 서버의 진실과 어긋난다.
 * `null`/`undefined`/공백 문자열만 '없음'이다.
 */
function firstProvided(...candidates: (string | number | null | undefined)[]): string {
  for (const candidate of candidates) {
    if (candidate === null || candidate === undefined) continue;
    const text = String(candidate).trim();
    if (text !== '') return text;
  }
  return '';
}

/** 서버·브라우저 어디에도 값이 없을 때만 쓰는 화면 표시 기본값(제공된 값을 덮지 않는다). */
const DISPLAY_DEFAULTS = {
  searchEngine: 'searxng',
  dailyBudget: '50',
  hourlyLimit: '100',
} as const;

/**
 * 화면이 서버의 진실을 아는 단계 (CR-06).
 *
 * `loading → ready | load-error`, `ready → saving → ready | save-error`.
 * 서버의 진실을 모르는 단계(loading/load-error)에서는 저장을 허용하지 않는다.
 */
type SettingsPhase = 'loading' | 'ready' | 'load-error' | 'saving' | 'save-error';

interface SettingsFormState {
  phase: SettingsPhase;
  config: SettingsData;
  /** 입력 중에만 존재하는 메모리 상태 — 어떤 저장소에도 영속하지 않는다 (CR-05). */
  apiKeys: Record<string, string>;
  /** 서버가 보고한 provider별 '설정됨' 상태(원문·부분값 아님). */
  configuredKeys: Record<string, boolean>;
  /** 사용자가 명시적으로 삭제를 선택한 키(저장 시 별도 경로로 전송). */
  pendingDeleteKeys: string[];
  defaultModel: string;
  searchEngine: string;
  dailyBudget: string;
  hourlyLimit: string;
}

/** 서버의 진실로 폼을 채우는 값 묶음(phase는 전이로만 바뀐다). */
type SettingsHydration = Omit<SettingsFormState, 'phase'>;

type SettingsFormAction =
  | { type: 'loadStart' }
  | { type: 'hydrate'; value: SettingsHydration }
  | { type: 'loadError' }
  | { type: 'saveStart' }
  | { type: 'saveFailed' }
  | { type: 'saveSucceeded' }
  | { type: 'refreshServerFields'; value: SettingsData; defaultModel: string }
  | { type: 'setApiKey'; key: string; value: string }
  | { type: 'markDelete'; key: string }
  | { type: 'unmarkDelete'; key: string }
  | { type: 'clearApiKeys' }
  | { type: 'setConfiguredKeys'; value: Record<string, boolean> }
  | { type: 'setDefaultModel'; value: string }
  | { type: 'setSearchEngine'; value: string }
  | { type: 'setDailyBudget'; value: string }
  | { type: 'setHourlyLimit'; value: string };

const initialSettingsForm: SettingsFormState = {
  phase: 'loading',
  config: {},
  apiKeys: {},
  configuredKeys: {},
  pendingDeleteKeys: [],
  defaultModel: '',
  searchEngine: '',
  dailyBudget: '',
  hourlyLimit: '',
};

function settingsFormReducer(state: SettingsFormState, action: SettingsFormAction): SettingsFormState {
  switch (action.type) {
    case 'loadStart': return { ...state, phase: 'loading' };
    case 'hydrate': return { ...state, ...action.value, phase: 'ready' };
    case 'loadError': return { ...state, phase: 'load-error' };
    case 'saveStart': return { ...state, phase: 'saving' };
    case 'saveFailed': return { ...state, phase: 'save-error' };
    case 'saveSucceeded': return { ...state, phase: 'ready' };
    // 저장 후 재조회: 서버가 관리하는 값만 서버의 최신 값으로 바꾸고,
    // 사용자가 방금 저장한 로컬 선호 입력(검색 엔진·예산·한도)은 유지한다.
    case 'refreshServerFields': return {
      ...state,
      config: action.value,
      configuredKeys: action.value.api_keys_configured ?? {},
      defaultModel: action.defaultModel,
    };
    case 'setApiKey': return { ...state, apiKeys: { ...state.apiKeys, [action.key]: action.value } };
    case 'markDelete': return {
      ...state,
      apiKeys: { ...state.apiKeys, [action.key]: '' },
      pendingDeleteKeys: state.pendingDeleteKeys.includes(action.key)
        ? state.pendingDeleteKeys
        : [...state.pendingDeleteKeys, action.key],
    };
    case 'unmarkDelete': return {
      ...state,
      pendingDeleteKeys: state.pendingDeleteKeys.filter(key => key !== action.key),
    };
    // 키는 메모리에서도 지운다(성공 저장·페이지 이탈).
    case 'clearApiKeys': return { ...state, apiKeys: {}, pendingDeleteKeys: [] };
    case 'setConfiguredKeys': return { ...state, configuredKeys: action.value };
    case 'setDefaultModel': return { ...state, defaultModel: action.value };
    case 'setSearchEngine': return { ...state, searchEngine: action.value };
    case 'setDailyBudget': return { ...state, dailyBudget: action.value };
    case 'setHourlyLimit': return { ...state, hourlyLimit: action.value };
  }
}

const SettingsPage: React.FC = () => {
  const { accentColor, fontSize, showMinimap, wordWrap, tabSize, setPref, reset: resetTheme } = useThemeStore();
  const { autoSaveEnabled, setAutoSaveEnabled } = useLocalHistoryStore();
  const [
    { phase, config, apiKeys, configuredKeys, pendingDeleteKeys, defaultModel, searchEngine, dailyBudget, hourlyLimit },
    dispatch,
  ] = useReducer(settingsFormReducer, initialSettingsForm);
  const [statusMsg, setStatusMsg] = useState('');
  const [currentPin, setCurrentPin] = useState('');
  const [newPin, setNewPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [pinStatusMsg, setPinStatusMsg] = useState('');
  const [pinBusy, setPinBusy] = useState(false);
  const [mobileGuideOpen, setMobileGuideOpen] = useState(() => {
    try {
      return window.localStorage.getItem('agk_mobile_lan_guide') === '1';
    } catch {
      return false;
    }
  });
  const [networkInfo, setNetworkInfo] = useState<NetworkAccessInfo | null>(null);
  const [networkInfoError, setNetworkInfoError] = useState('');
  const [networkInfoBusy, setNetworkInfoBusy] = useState(false);
  /** 진행 중 저장 요청 표시(연속 클릭 방지) — 렌더 전에 동기적으로 막는다. */
  const savingRef = useRef(false);
  /** 서버가 실제로 강제하는 비용 한도 — 화면은 읽기 전용 맥락으로만 보여준다. */
  const serverDailyBudget = firstProvided(config.cost?.daily_budget_usd);
  const serverHourlyLimit = firstProvided(config.cost?.hourly_action_limit);

  /**
   * 서버가 준 설정으로 폼을 채운다 (CR-06).
   *
   * 서버가 관리하는 값(model.name·cost.*)이 우선이고, 브라우저에 남아 있는
   * 오래된 값은 서버가 그 값을 주지 않을 때만 쓴다.
   */
  const hydrateFromServer = useCallback((cfg: SettingsData) => {
    // CR-05: 브라우저에는 비밀 아닌 preference만 남긴다.
    const savedPrefs = readBrowserSettings();
    const cost = cfg.cost ?? {};
    dispatch({
      type: 'hydrate',
      value: {
        config: cfg,
        // 서버는 마스킹 값이 아니라 provider별 '설정됨' 상태만 준다.
        configuredKeys: cfg.api_keys_configured ?? {},
        pendingDeleteKeys: [],
        apiKeys: {},
        defaultModel: firstProvided(cfg.model?.name) || firstProvided(savedPrefs.default_model),
        searchEngine: firstProvided(savedPrefs.search_engine) || DISPLAY_DEFAULTS.searchEngine,
        // 서버의 0은 유효한 한도다 — 기본값으로 바꾸지 않는다.
        dailyBudget:
          firstProvided(cost.daily_budget_usd) ||
          firstProvided(savedPrefs.daily_budget_usd) ||
          DISPLAY_DEFAULTS.dailyBudget,
        hourlyLimit:
          firstProvided(cost.hourly_action_limit) ||
          firstProvided(savedPrefs.hourly_action_limit) ||
          DISPLAY_DEFAULTS.hourlyLimit,
      },
    });
  }, []);

  const loadSettings = useCallback(async () => {
    dispatch({ type: 'loadStart' });
    try {
      hydrateFromServer(await fetchSettings());
    } catch {
      // 기본값 폼을 정상 설정처럼 보여주지 않는다 — 재시도 전에는 저장 금지.
      dispatch({ type: 'loadError' });
    }
  }, [hydrateFromServer]);

  /**
   * provider별 '설정됨' 상태만 다시 읽는다(task 14).
   *
   * 통합 검색 패널이 토큰을 저장한 뒤 부른다 — 그 패널이 자기만의 `/api/settings` 를 갖지 않게
   * 하려고(왕복 중복 + 두 시점의 진실) 이 페이지가 계속 소유한다.
   */
  const refreshConfiguredKeys = useCallback(() => {
    void (async () => {
      try {
        const refreshed = await fetchSettings();
        dispatch({ type: 'setConfiguredKeys', value: refreshed.api_keys_configured ?? {} });
      } catch {
        // 토큰 상태를 못 읽는다고 방금 성공한 저장을 실패로 바꾸지 않는다.
      }
    })();
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  // 키는 입력 중에만 메모리에 둔다 — 페이지 이탈/언마운트에서 지운다.
  useEffect(() => {
    const clearKeys = () => dispatch({ type: 'clearApiKeys' });
    window.addEventListener('pagehide', clearKeys);
    return () => {
      window.removeEventListener('pagehide', clearKeys);
      dispatch({ type: 'clearApiKeys' });
    };
  }, []);

  const handleSave = async () => {
    // 서버의 진실을 모르는 동안(loading/load-error)에는 저장하지 않는다(C06-01).
    if (phase === 'loading' || phase === 'load-error') return;
    // 진행 중인 요청이 있으면 연속 클릭을 무시한다(중복 요청 금지, C06-03).
    if (savingRef.current) return;

    // 비밀 아닌 preference만 브라우저에 저장한다(API 키는 저장하지 않는다).
    writeBrowserSettings({
      default_model: defaultModel,
      search_engine: searchEngine,
      daily_budget_usd: dailyBudget,
      hourly_action_limit: hourlyLimit,
    });

    // 비어 있는 입력은 **전송하지 않는다**(기존 서버 키 유지).
    const keyUpdates: Record<string, string> = {};
    for (const provider of PROVIDERS) {
      const value = apiKeys[provider.key];
      if (value) keyUpdates[provider.key] = value;
    }
    // 새 값을 입력한 키는 삭제 대상이 아니다.
    const keyDeletions = pendingDeleteKeys.filter(key => !keyUpdates[key]);

    if (Object.keys(keyUpdates).length === 0 && keyDeletions.length === 0) {
      setStatusMsg('✅ 브라우저 설정을 저장했습니다. (서버로 보낼 API 키 변경 없음)');
      return;
    }

    savingRef.current = true;
    dispatch({ type: 'saveStart' });
    setStatusMsg('⏳ 저장 중...');

    try {
      let updated = 0;
      let deleted = 0;
      if (Object.keys(keyUpdates).length > 0) {
        const data = await saveSettings(keyUpdates);
        if (!data.ok) {
          dispatch({ type: 'saveFailed' });
          setStatusMsg(`⚠️ ${data.error || data.detail || '저장 실패 — PIN/권한을 확인하세요'}`);
          return;
        }
        updated = data.updated ?? 0;
      }
      if (keyDeletions.length > 0) {
        const deletionResult = await deleteSettingsKeys(keyDeletions);
        deleted = deletionResult.deleted ?? 0;
      }
      // 성공 저장 후에는 입력값을 지우고(원문 재주입 없음), 서버 관리 값을 재조회한다.
      dispatch({ type: 'clearApiKeys' });
      dispatch({ type: 'saveSucceeded' });
      let refreshNote = '';
      try {
        const refreshed = await fetchSettings();
        dispatch({
          type: 'refreshServerFields',
          value: refreshed,
          defaultModel: firstProvided(refreshed.model?.name) || defaultModel,
        });
      } catch {
        refreshNote = ' (서버 값 재조회 실패)'; // 저장 자체는 성공했다.
      }
      setStatusMsg(`✅ 저장 완료! 키 ${updated}건 갱신, ${deleted}건 삭제 (서버 재시작 후 적용)${refreshNote}`);
    } catch (error) {
      dispatch({ type: 'saveFailed' });
      // 401은 client가 agk:pin-required 이벤트를 쏘아 기존 PIN 모달을 연다.
      setStatusMsg(
        isAuthRequiredError(error)
          ? '🔒 PIN 인증이 필요합니다. 잠금을 해제한 뒤 다시 저장하세요.'
          : `⚠️ 서버 저장 실패: ${errorMessage(error)}`,
      );
    } finally {
      savingRef.current = false;
    }
  };

  const handleReset = () => {
    if (
      confirm(
        '브라우저에 저장된 일반 설정(모델·검색 엔진·비용 한도)을 초기화하시겠습니까?\n서버에 저장된 API 키는 각 항목의 삭제 버튼으로 지웁니다.',
      )
    ) {
      writeBrowserSettings({});
      window.location.reload();
    }
  };

  const persistMobileGuide = useCallback((on: boolean) => {
    setMobileGuideOpen(on);
    try {
      window.localStorage.setItem('agk_mobile_lan_guide', on ? '1' : '0');
    } catch {
      /* ignore quota / private mode */
    }
  }, []);

  const loadNetworkAccessInfo = useCallback(async () => {
    setNetworkInfoBusy(true);
    setNetworkInfoError('');
    try {
      setNetworkInfo(await fetchNetworkAccessInfo());
    } catch (error) {
      setNetworkInfo(null);
      setNetworkInfoError(errorMessage(error));
    } finally {
      setNetworkInfoBusy(false);
    }
  }, []);

  useEffect(() => {
    if (mobileGuideOpen) {
      void loadNetworkAccessInfo();
    }
  }, [mobileGuideOpen, loadNetworkAccessInfo]);

  const handleChangePin = useCallback(async () => {

    setPinStatusMsg('');
    const current = currentPin.trim();
    const next = newPin.trim();
    const confirmed = confirmPin.trim();
    if (!current || !next || !confirmed) {
      setPinStatusMsg('⚠️ 현재 PIN과 새 PIN을 모두 입력하세요.');
      return;
    }
    if (next.length < 4 || next.length > 128) {
      setPinStatusMsg('⚠️ 새 PIN은 4–128자여야 합니다.');
      return;
    }
    if (next !== confirmed) {
      setPinStatusMsg('⚠️ 새 PIN과 확인 값이 일치하지 않습니다.');
      return;
    }
    if (pinBusy) return;
    setPinBusy(true);
    try {
      const result = await changeAccessPin(current, next);
      setCurrentPin('');
      setNewPin('');
      setConfirmPin('');
      if (result.reauthRequired) {
        // NX-05: 이 시점부터 이 브라우저의 토큰은 서버 세대와 다르다(전체 폐기).
        // 토큰을 남겨두면 모든 요청이 401로 반복되므로 즉시 지우고 재로그인을 띄운다.
        clearAccessCredential();
        setPinStatusMsg('✅ PIN이 변경되었습니다. 보안을 위해 모든 세션이 종료되었습니다 — 새 PIN으로 다시 로그인하세요.');
        // NX-09: 모달이 앱 전체를 대체하므로 위 상태 메시지는 사라진다 — 이유를 모달이 들고 간다.
        useUiStore.getState().setPinModalNotice(
          '보안을 위해 모든 세션이 종료되었습니다. 새 PIN으로 다시 로그인하세요.',
        );
        useUiStore.getState().setPinModalVisible(true);
        return;
      }
      setPinStatusMsg(`✅ ${result.detail || 'PIN이 변경되었습니다.'}`);
    } catch (error) {
      if (isAuthRequiredError(error)) {
        setPinStatusMsg('🔒 PIN 인증이 필요합니다. 잠금을 해제한 뒤 다시 시도하세요.');
      } else {
        setPinStatusMsg(`⚠️ PIN 변경 실패: ${errorMessage(error)}`);
      }
    } finally {
      setPinBusy(false);
    }
  }, [confirmPin, currentPin, newPin, pinBusy]);

  // 서버의 진실을 확인하기 전 단계 — 폼을 렌더하지 않으므로 저장할 수 없다(C06-01).
  if (phase === 'loading') {
    return (
      <div className="page-container">
        <div className="loading-state" data-testid="settings-loading">설정 불러오는 중...</div>
      </div>
    );
  }

  if (phase === 'load-error') {
    return (
      <div className="page-container" style={{ maxWidth: 640, margin: '0 auto' }}>
        <GlassPanel title={<><span className="section-index">01</span> 설정을 불러오지 못했습니다</>} variant="section">
          <div data-testid="settings-load-error" role="alert" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <p className="settings-desc" style={{ margin: 0 }}>
              서버에서 현재 설정을 읽지 못했습니다. 이 상태에서는 <strong>기본값을 정상 설정처럼 저장할 수 없습니다</strong>.
            </p>
            <p className="settings-desc" style={{ margin: 0, fontSize: 12 }}>
              서버가 실행 중인지, 인증(PIN)이 필요한 상태인지 확인한 뒤 다시 시도하세요.
            </p>
            <div>
              <button type="button" className="btn-primary" data-testid="settings-retry" onClick={() => void loadSettings()}>
                ↻ 다시 시도
              </button>
            </div>
          </div>
        </GlassPanel>
      </div>
    );
  }


  return (
    <div className="settings-page" style={{ maxWidth: 860, margin: '0 auto' }}>
      <div className="page-header" style={{ marginBottom: 32 }}>
        <div className="page-header-hero">
          <div className="hero-eyebrow">CONFIGURATION</div>
          <h2>시스템 설정</h2>
          <p className="page-subtitle">API 키, 모델, 검색 엔진, 비용 제어를 한 곳에서 관리합니다.</p>
        </div>
      </div>

      <div id="settings-container" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

        {/* 1. API Keys */}
        <GlassPanel title={<><span className="section-index">01</span> API 키 설정</>} variant="section" className="settings-section">
          <p className="settings-desc">
            사용할 프로바이더의 API 키를 입력하세요. 키는 <strong>입력 중에만 메모리에</strong> 있고,
            저장하면 서버로만 전송됩니다 — 브라우저에는 남지 않습니다. 반영에는 서버 재시작이 필요합니다.
          </p>
          <p className="settings-desc" style={{ marginTop: -6, fontSize: 12 }}>
            이전 버전에서 브라우저에 저장된 키는 자동으로 전송되지 않으며, 제거되었을 수 있으니 필요하면 다시 입력하세요.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {PROVIDERS.map(p => {
              const configured = configuredKeys[p.key] === true;
              const pendingDelete = pendingDeleteKeys.includes(p.key);
              const typed = apiKeys[p.key] ?? '';
              const isSet = configured && !pendingDelete;
              return (
                <div key={p.key} className="settings-row">
                  <div className="settings-row-label">
                    {/* CR-08(F04-a): 위 입력의 aria-labelledby 대상 — 보이는 이름을 그대로 쓴다. */}
                    <div className="settings-row-title" id={`api-key-label-${p.key}`}>{p.icon} {p.label}</div>
                    <div className="settings-row-hint">{p.hint}</div>
                  </div>
                  <input
                    type="password"
                    autoComplete="off"
                    className="text-input settings-row-input"
                    data-testid={`api-key-input-${p.key}`}
                    id={`api-key-input-${p.key}`}
                    /*
                     * CR-08(F04-a): 여섯 provider 입력의 접근성 이름이 placeholder로
                     * 같아져 화면 낭독으로 구분할 수 없었다. 보이는 provider 이름을
                     * aria-labelledby로 연결해 고유한 이름을 준다.
                     */
                    aria-labelledby={`api-key-label-${p.key}`}
                    placeholder={isSet ? '•••••••• (새 값을 입력하면 교체됩니다)' : 'API 키 입력'}
                    value={typed}
                    onChange={e => dispatch({ type: 'setApiKey', key: p.key, value: e.target.value })}
                  />
                  <div className="settings-row-status" style={{ width: 150, textAlign: 'right' }}>
                    {isSet
                      ? <span className="status-badge success">✓ 설정됨</span>
                      : <span className="status-badge muted">⚪ 미설정</span>}
                    {configured && (
                      pendingDelete
                        ? (
                          <button
                            type="button"
                            className="btn-ghost"
                            data-testid={`api-key-undo-${p.key}`}
                            onClick={() => dispatch({ type: 'unmarkDelete', key: p.key })}
                          >
                            삭제 취소
                          </button>
                        )
                        : (
                          <button
                            type="button"
                            className="btn-ghost"
                            data-testid={`api-key-delete-${p.key}`}
                            onClick={() => dispatch({ type: 'markDelete', key: p.key })}
                          >
                            삭제
                          </button>
                        )
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </GlassPanel>

        {/* 2. Default Model */}
        <GlassPanel title={<><span className="section-index">02</span> 기본 모델</>} variant="section" className="settings-section">
          <div className="settings-row">
            <div className="settings-row-label">
              <div className="settings-row-title">🤖 기본 추론 모델</div>
              <div className="settings-row-hint">서버 구성(defaults.reasoning) 값을 보여줍니다</div>
            </div>
            <input
              type="text"
              data-testid="settings-default-model"
              className="text-input settings-row-input"
              placeholder="예: qwen3.6:latest, openai/gpt-4o-mini"
              value={defaultModel}
              onChange={e => dispatch({ type: 'setDefaultModel', value: e.target.value })}
            />
          </div>
        </GlassPanel>

        <ModelOperationsPanel />

        {/* 3. Search Engine — Toggle Switch */}
        <GlassPanel title={<><span className="section-index">03</span> 웹 검색 엔진</>} variant="section" className="settings-section">
          <p className="settings-desc">
            기본 검색 엔진을 선택하세요. 변경 사항은 즉시 적용됩니다.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {[
              { id: 'searxng', label: 'SearxNG', desc: '메타 검색 — Google+Bing+DDG 집계, 로컬' },
              { id: 'duckduckgo', label: 'DuckDuckGo', desc: '단일 엔진, 간단, 추가 설정 불필요' },
              { id: 'jina', label: 'Jina AI', desc: '시맨틱 검색, AI 친화적 결과' },
            ].map(engine => (
              <label key={engine.id} className="toggle-switch">
                <input
                  type="radio"
                  name="search_engine"
                  value={engine.id}
                  checked={searchEngine === engine.id}
                  onChange={() => dispatch({ type: 'setSearchEngine', value: engine.id })}
                />
                <span className="toggle-track" />
                <span className="toggle-label">
                  {engine.label}
                  <small>{engine.desc}</small>
                </span>
              </label>
            ))}
          </div>
        </GlassPanel>

        {/*
         * 03B. 통합 검색 (task 14) — 번들 provider 의 켜기/끄기·상태·증거.
         *
         * 별도 컴포넌트인 이유: 이 패널의 진실은 `/api/search/*`(설정 스냅숏 + 런타임 상태)이고
         * 이 페이지의 폼 상태(apiKeys/모델/비용)와 수명이 다르다 — 한 reducer 에 섞으면 저장
         * 단위가 달라지는 순간 둘이 서로를 덮어쓴다.
         */}
        <SearchIntegrationPanel
          engineTokenConfigured={configuredKeys.AGK_SEARCH_ENGINE_TOKEN === true}
          onEngineTokenSaved={refreshConfiguredKeys}
        />

        {/* 4. Cost Control */}
        <GlassPanel title={<><span className="section-index">04</span> 비용 제어</>} variant="section" className="settings-section">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* 현재 한도 상태 고지 (설정 입력 바로 위) */}
            <SessionDisclosurePanel />
            {/* CR-06: 서버가 실제로 강제하는 한도를 read-only로 보여준다. */}
            <div className="settings-desc" data-testid="settings-server-cost" style={{ margin: 0, fontSize: 12 }}>
              서버 강제 한도: 일일 ${serverDailyBudget || '미설정'} · 시간당 {serverHourlyLimit || '미설정'} 액션
              <span style={{ opacity: 0.75 }}> (config.yaml `cost` / `AGK_DAILY_BUDGET_USD`·`AGK_HOURLY_ACTION_LIMIT`, 서버 재시작 후 반영)</span>
            </div>
            <div className="settings-row">
              <div className="settings-row-label">
                <div className="settings-row-title">💰 일일 예산 (USD)</div>
                <div className="settings-row-hint">이 브라우저에 저장되는 표시 선호 — 서버 한도는 위 값을 따른다</div>
              </div>
                  {/* UI-01 (axe label): number 입력에 접근 가능한 이름 제공 */}
                  <input type="number" data-testid="settings-daily-budget" aria-label="일일 예산 (USD)" className="text-input settings-row-input-narrow" value={dailyBudget} onChange={e => dispatch({ type: 'setDailyBudget', value: e.target.value })} />
            </div>
            <div className="settings-row">
              <div className="settings-row-label">
                <div className="settings-row-title">⏱ 시간당 액션 한도</div>
                <div className="settings-row-hint">이 브라우저에 저장되는 표시 선호 — 서버 한도는 위 값을 따른다</div>
              </div>
                  <input type="number" data-testid="settings-hourly-limit" aria-label="시간당 액션 한도" className="text-input settings-row-input-narrow" value={hourlyLimit} onChange={e => dispatch({ type: 'setHourlyLimit', value: e.target.value })} />
            </div>
          </div>
        </GlassPanel>

        {/* Access PIN change */}
        <GlassPanel title={<><span className="section-index">PIN</span> 액세스 PIN 변경</>} variant="section" className="settings-section">
          <p className="settings-desc">
            로그인 후 액세스 PIN을 변경합니다. 새 PIN은 4자 이상이어야 합니다.
            (서버 최초 부트스트랩용 plaintext는 non-loopback에서 8자 규칙이 유지됩니다.)
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 420 }}>
            <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
              <label className="settings-field-label" htmlFor="settings-current-pin">현재 PIN</label>
              <input
                id="settings-current-pin"
                data-testid="settings-current-pin"
                type="password"
                autoComplete="current-password"
                className="text-input"
                value={currentPin}
                onChange={e => setCurrentPin(e.target.value)}
                aria-label="현재 PIN"
              />
            </div>
            <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
              <label className="settings-field-label" htmlFor="settings-new-pin">새 PIN</label>
              <input
                id="settings-new-pin"
                data-testid="settings-new-pin"
                type="password"
                autoComplete="new-password"
                className="text-input"
                value={newPin}
                onChange={e => setNewPin(e.target.value)}
                aria-label="새 PIN"
              />
            </div>
            <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
              <label className="settings-field-label" htmlFor="settings-confirm-pin">새 PIN 확인</label>
              <input
                id="settings-confirm-pin"
                data-testid="settings-confirm-pin"
                type="password"
                autoComplete="new-password"
                className="text-input"
                value={confirmPin}
                onChange={e => setConfirmPin(e.target.value)}
                aria-label="새 PIN 확인"
              />
            </div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <button
                type="button"
                className="btn-primary"
                data-testid="settings-change-pin"
                disabled={pinBusy}
                onClick={() => { void handleChangePin(); }}
              >
                {pinBusy ? '변경 중…' : 'PIN 변경'}
              </button>
              {pinStatusMsg && (
                <div
                  role={pinStatusMsg.startsWith('✅') ? 'status' : 'alert'}
                  data-testid="settings-pin-status"
                  style={{ fontSize: 12, flex: 1 }}
                >
                  {pinStatusMsg}
                </div>
              )}
            </div>
          </div>
        </GlassPanel>


        {/* Mobile / LAN access (personal use) — guide only; bind change needs Host restart */}
        <GlassPanel title={<><span className="section-index">모바일</span> 모바일·LAN 접속 (개인용)</>} variant="section" className="settings-section">
          <p className="settings-desc">
            기본은 이 Mac의 <code>127.0.0.1</code>만 사용합니다. 폰에서 쓰려면 Host를 사설망에
            열고 PIN으로 로그인하세요. 불특정 인터넷 공개는 권장하지 않습니다.
          </p>
          <label className="toggle-switch" style={{ marginBottom: 12 }}>
            <input
              type="checkbox"
              data-testid="settings-mobile-guide-toggle"
              checked={mobileGuideOpen}
              onChange={e => persistMobileGuide(e.target.checked)}
            />
            <span className="toggle-track" />
            <span className="toggle-label">모바일 접속 안내 표시 (기본 OFF · 브라우저 기억)</span>
          </label>
          {mobileGuideOpen && (
            <div data-testid="settings-mobile-guide" style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 560 }}>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                1) PIN이 설정돼 있는지 확인 · 2) Host를 재시작할 때 non-loopback으로 bind ·
                3) 폰 브라우저로 아래 URL 접속 · 4) 가능하면 Tailscale 사용
              </div>
              {networkInfoBusy && <div style={{ fontSize: 12 }}>네트워크 정보 불러오는 중…</div>}
              {networkInfoError && (
                <div role="alert" style={{ fontSize: 12, color: '#ff6b6b' }}>조회 실패: {networkInfoError}</div>
              )}
              {networkInfo && (
                <>
                  <div style={{ fontSize: 12 }}>
                    현재 bind: <code>{networkInfo.bind_host}:{networkInfo.port}</code>
                    {networkInfo.is_loopback ? ' (loopback · 폰에서 직접 접속 불가)' : ' (non-loopback)'}
                  </div>
                  <div style={{ fontSize: 12 }}>
                    재시작 예시: <code>{networkInfo.restart_command_lan}</code>
                  </div>
                  {networkInfo.suggested_mobile_urls.length > 0 ? (
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                      {networkInfo.suggested_mobile_urls.map(url => (
                        <li key={url}><code>{url}</code></li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ fontSize: 12 }}>감지된 LAN IP가 없습니다. Tailscale IP 또는 라우터 할당 주소를 직접 입력하세요.</div>
                  )}
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: 'var(--text-secondary)' }}>
                    {networkInfo.notes.map(note => <li key={note}>{note}</li>)}
                  </ul>
                </>
              )}
              <button
                type="button"
                className="btn-secondary"
                data-testid="settings-mobile-refresh"
                disabled={networkInfoBusy}
                onClick={() => { void loadNetworkAccessInfo(); }}
              >
                네트워크 정보 새로고침
              </button>
            </div>
          )}
        </GlassPanel>

        {/* 5. Local History Settings */}
        <GlassPanel title={<><span className="section-index">05</span> 로컬 히스토리</>} variant="section" className="settings-section">
          <p className="settings-desc">
            파일 변경 내역을 자동으로 저장하여 이전 상태로 되돌리거나 비교할 수 있습니다.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={autoSaveEnabled}
                onChange={e => setAutoSaveEnabled(e.target.checked)}
              />
              <span className="toggle-track" />
              <span className="toggle-label">
                자동 스냅샷 저장
                <small>파일이 변경될 때마다 현재 상태를 히스토리에 저장합니다</small>
              </span>
            </label>
          </div>
        </GlassPanel>

        {/* 6. Theme Customization */}
        <GlassPanel title={<><span className="section-index">06</span> 테마 설정</>} variant="section" className="settings-section">
          <p className="settings-desc">
            에디터와 인터페이스의 모양을 커스터마이즈합니다.
          </p>

          {/* Accent Color */}
          <div style={{ marginBottom: 20 }}>
            <label className="settings-field-label">강조 색상</label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {THEME_COLORS.map(color => (
                <button
                  key={color}
                  className="theme-color-swatch"
                  onClick={() => setPref('accentColor', color)}
                  style={{
                    width: 32, height: 32, borderRadius: '50%',
                    background: color,
                    border: accentColor === color ? '3px solid #fff' : '3px solid transparent',
                    boxShadow: accentColor === color ? `0 0 12px ${color}` : 'none',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                  title={color}
                  aria-label={`강조 색상: ${color}`}
                  aria-pressed={accentColor === color}
                />
              ))}
            </div>
          </div>

          {/* Font Size */}
          <div style={{ marginBottom: 20 }}>
            <label className="settings-field-label">에디터 폰트 크기</label>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {FONT_SIZES.map(size => (
                <button
                  key={size}
                  className={`btn-ghost font-size-btn ${fontSize === size ? 'active' : ''}`}
                  onClick={() => setPref('fontSize', size)}
                  style={{ fontSize: size > 14 ? 12 : 11 }}
                  aria-pressed={fontSize === size}
                >
                  {size}px
                </button>
              ))}
            </div>
          </div>

          {/* Editor Options */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label className="toggle-switch">
              <input type="checkbox" checked={showMinimap} onChange={e => setPref('showMinimap', e.target.checked)} />
              <span className="toggle-track" />
              <span className="toggle-label">미니맵 표시</span>
            </label>

            <div className="settings-row">
              <span className="settings-row-label-text">탭 크기</span>
              <select
                className="glass-select"
                value={tabSize}
                onChange={e => setPref('tabSize', parseInt(e.target.value))}
                style={{ minWidth: 80 }}
                aria-label="탭 크기"
              >
                <option value={2}>2</option>
                <option value={4}>4</option>
                <option value={8}>8</option>
              </select>
            </div>

            <div className="settings-row">
              <span className="settings-row-label-text">자동 줄바꿈</span>
              <select
                className="glass-select"
                value={wordWrap}
                onChange={e => setPref('wordWrap', e.target.value as 'on' | 'off')}
                style={{ minWidth: 80 }}
                aria-label="자동 줄바꿈"
              >
                <option value="on">On</option>
                <option value="off">Off</option>
              </select>
            </div>
          </div>

          {/* Reset Theme */}
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--glass-border)' }}>
            <button className="btn-ghost" onClick={resetTheme}>
              🎨 테마 초기화
            </button>
          </div>
        </GlassPanel>

        {/* 📦 Cache Stats */}
        <CacheStatsPanel />

        {/* 🔌 MCP Health Cache */}
        <McpHealthCachePanel />

        {/* 🔐 MCP OAuth 2.1 */}
        <McpOAuthPanel />

        {/* 🔬 Log Level / Debug Mode */}
        <LogLevelSection />

        {/* 6. Server Config (read-only) */}
        <GlassPanel title={<><span className="section-index">07</span> 서버 구성 (읽기 전용)</>} variant="section" className="settings-section" style={{ opacity: 0.8 }}>
          <div style={{ opacity: 0.8 }}>
            <div className="server-config-grid">
              <div className="settings-row-label-text">호스트</div>
              <div>{config.server?.host || '127.0.0.1'}</div>
              <div className="settings-row-label-text">포트</div>
              <div>{config.server?.port || '8000'}</div>
              <div className="settings-row-label-text">API 엔진</div>
              <div>{config.model?.provider || 'openrouter'}</div>
            </div>
          </div>
        </GlassPanel>

        {/* Save / Reset */}
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', alignItems: 'center', paddingTop: 8 }}>
          {statusMsg && (
            phase === 'save-error'
              ? (
                <div
                  role="alert"
                  data-testid="settings-save-error"
                  style={{ fontSize: 12, flex: 1, textAlign: 'left', minHeight: 18, color: 'var(--text-warning, #f59e0b)' }}
                >
                  {statusMsg}
                </div>
              )
              : (
                <div
                  role="status"
                  data-testid="settings-status"
                  style={{ fontSize: 12, flex: 1, textAlign: 'left', minHeight: 18 }}
                >
                  {statusMsg}
                </div>
              )
          )}
          <button className="btn-ghost" onClick={handleReset}>
            🗑️ 초기화
          </button>
          <button
            className={`btn-primary save-anim ${phase === 'saving' ? 'saving' : ''}`}
            data-testid="settings-save"
            onClick={handleSave}
            disabled={phase === 'saving'}
          >
            {phase === 'saving' ? (
              <><span className="spinner spinner-sm" /> 저장 중...</>
            ) : (
              '💾 설정 저장'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;

// ─── Log Level Section ─────────────────────────────────────────

const LOG_LEVEL_OPTIONS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

const LogLevelSection: React.FC = () => {
  const [loggers, setLoggers] = useState<LogLevelInfo[]>([]);
  const [debugMode, setDebugModeState] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedLogger, setSelectedLogger] = useState('antigravity_k.api');
  const [selectedLevel, setSelectedLevel] = useState('INFO');
  const [logMsg, setLogMsg] = useState('');
  const [expanded, setExpanded] = useState(false);

  const applyLogLevelData = (data: Awaited<ReturnType<typeof fetchLogLevels>>) => {
    if (data.ok) {
      setLoggers(data.loggers);
      setDebugModeState(data.debug_mode);
    }
  };

  const loadLogLevels = async () => {
    setLoading(true);
    try {
      applyLogLevelData(await fetchLogLevels());
    } catch {
      setLogMsg('⚠️ 로그 레벨을 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    void fetchLogLevels()
      .then(data => {
        if (active) applyLogLevelData(data);
      })
      .catch(() => {
        if (active) setLogMsg('⚠️ 로그 레벨을 불러오는데 실패했습니다.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const handleSetLevel = async () => {
    try {
      const data = await setLogLevel(selectedLogger, selectedLevel);
      if (data.ok) {
        setLogMsg(`✅ ${selectedLogger} → ${selectedLevel}`);
        loadLogLevels();
      } else {
        setLogMsg(`⚠️ ${data.error || '설정 실패'}`);
      }
    } catch (error) {
      setLogMsg(`⚠️ 네트워크 오류: ${errorMessage(error)}`);
    }
  };

  const handleSetAllLevels = async (level: string) => {
    try {
      const data = await setAllLogLevels(level);
      if (data.ok) {
        setLogMsg(`✅ 모든 로거 → ${level} (${data.result?.updated_count || 0}개)`);
        loadLogLevels();
      } else {
        setLogMsg(`⚠️ ${data.error || '설정 실패'}`);
      }
    } catch (error) {
      setLogMsg(`⚠️ 네트워크 오류: ${errorMessage(error)}`);
    }
  };

  const handleToggleDebug = async () => {
    try {
      const action = debugMode ? 'disable' : 'enable';
      const data = await setDebugMode(action);
      if (data.ok) {
        setDebugModeState(data.debug_mode);
        setLogMsg(`🔍 ${data.result?.message || '디버그 모드 전환 완료'}`);
        loadLogLevels();
      } else {
        setLogMsg(`⚠️ ${data.error || '전환 실패'}`);
      }
    } catch (error) {
      setLogMsg(`⚠️ 네트워크 오류: ${errorMessage(error)}`);
    }
  };

  // Filter to show only loggers with explicit level set (non-default)
  const visibleLoggers = expanded ? loggers : loggers.slice(0, 8);
  const hasMore = loggers.length > 8;

  // Summary stats
  const debugCount = loggers.filter(l => l.level_name === 'DEBUG').length;
  const infoCount = loggers.filter(l => l.level_name === 'INFO').length;
  const warnCount = loggers.filter(l => l.level_name === 'WARNING').length;
  const errorCount = loggers.filter(l => l.level_name === 'ERROR' || l.level_name === 'CRITICAL').length;

  return (
    <GlassPanel title={<><span className="section-index">08</span> 로그 레벨 / 디버그 모드</>} variant="section" className="settings-section">
      <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
        서버 재시작 없이 로깅 레벨을 동적으로 변경합니다. 디버그 모드는 모든 로거를 DEBUG로 설정합니다.
      </p>

      {/* Debug Mode Toggle + Quick Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <button
          className={`btn-secondary ${debugMode ? 'danger' : ''}`}
          onClick={handleToggleDebug}
          style={{
            minWidth: 140,
            background: debugMode ? 'rgba(248,81,73,0.2)' : undefined,
            borderColor: debugMode ? 'rgba(248,81,73,0.4)' : undefined,
          }}
        >
          {debugMode ? '🔴 디버그 모드 ON' : '🟢 디버그 모드 OFF'}
        </button>

        <div style={{ width: 1, height: 24, background: 'var(--glass-border)' }} />

        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>퀵 액션:</span>
        <button className="btn-ghost" onClick={() => handleSetAllLevels('DEBUG')} title="모든 로거 DEBUG">
          🔍 전체 DEBUG
        </button>
        <button className="btn-ghost" onClick={() => handleSetAllLevels('INFO')} title="모든 로거 INFO">
          ℹ️ 전체 INFO
        </button>
        <button className="btn-ghost" onClick={() => { void loadLogLevels(); }} title="새로고침">
          🔄 새로고침
        </button>
      </div>

      {/* Summary Bar */}
      <div style={{
        display: 'flex', gap: 8, marginBottom: 12,
        fontSize: 11, color: 'var(--text-secondary)',
      }}>
        <span>🔍 DEBUG {debugCount}개</span>
        <span>ℹ️ INFO {infoCount}개</span>
        <span>⚠️ WARN {warnCount}개</span>
        <span>❌ ERROR {errorCount}개</span>
      </div>

      {/* Individual Logger Control */}
      <div style={{
        display: 'flex', gap: 8, alignItems: 'center',
        marginBottom: 12, padding: 8,
        background: 'rgba(0,0,0,0.15)', borderRadius: 6,
        border: '1px solid var(--glass-border)',
      }}>
        <select
          className="glass-select"
          value={selectedLogger}
          onChange={e => setSelectedLogger(e.target.value)}
          style={{ flex: 1, fontSize: 12, padding: '6px 8px' }}
          aria-label="로거 선택"
        >
          {loggers.map(l => (
            <option key={l.name} value={l.name}>
              {l.name} ({l.level_name})
            </option>
          ))}
        </select>

        <select
          className="glass-select"
          value={selectedLevel}
          onChange={e => setSelectedLevel(e.target.value)}
          style={{ width: 100, fontSize: 12, padding: '6px 8px' }}
          aria-label="로그 레벨"
        >
          {LOG_LEVEL_OPTIONS.map(l => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>

        <button className="btn-primary" onClick={handleSetLevel}>
          적용
        </button>
      </div>

      {/* Logger List */}
      {loading ? (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>
          로그 레벨 불러오는 중...
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {visibleLoggers.map(l => (
              <div
                key={l.name}
                className="settings-logger-row"
                style={{
                  display: 'flex', justifyContent: 'space-between',
                  alignItems: 'center', padding: '4px 8px',
                  fontSize: 11, fontFamily: "'JetBrains Mono', monospace",
                  borderRadius: 4,
                  background: l.level_name === 'DEBUG' ? 'rgba(88,166,255,0.08)' :
                              l.level_name === 'WARNING' ? 'rgba(210,153,34,0.08)' :
                              l.level_name === 'ERROR' || l.level_name === 'CRITICAL' ? 'rgba(248,81,73,0.08)' :
                              'transparent',
                }}
              >
                <span className="settings-logger-name" style={{ color: 'var(--text-secondary)' }}>
                  {l.name}
                  {l.handlers > 0 && (
                    <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 6 }}>
                      ({l.handlers}h)
                    </span>
                  )}
                </span>
                <span className="settings-logger-level" style={{
                  fontWeight: 600,
                  color: l.level_name === 'DEBUG' ? '#58a6ff' :
                         l.level_name === 'WARNING' ? '#d29922' :
                         l.level_name === 'ERROR' ? '#f85149' :
                         l.level_name === 'CRITICAL' ? '#f85149' :
                         'var(--text-primary)',
                }}>
                  {l.level_name}
                  {l.level !== l.effective_level && l.level === 0 && (
                    <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 4 }}>
                      (→{l.effective_level_name})
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>

          {hasMore && (
            <button
              className="btn-ghost"
              onClick={() => setExpanded(!expanded)}
              style={{ width: '100%', marginTop: 8, fontSize: 11 }}
            >
              {expanded ? `▲ 접기` : `▼ ${loggers.length - 8}개 더 보기`}
            </button>
          )}
        </>
      )}

      {/* Status Message */}
      {logMsg && (
        <div style={{
          marginTop: 8, fontSize: 11, padding: '6px 8px',
          borderRadius: 4,
          background: logMsg.startsWith('✅') ? 'rgba(16,185,129,0.1)' : 'rgba(248,81,73,0.1)',
        }}>
          {logMsg}
          <button
            className="btn-ghost"
            onClick={() => setLogMsg('')}
            style={{ float: 'right', fontSize: 10, padding: '2px 6px' }}
          >
            ✕
          </button>
        </div>
      )}
    </GlassPanel>
  );
};

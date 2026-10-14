"""i18n — 에이전트 다국어 지원 시스템.

===================================

tiptap-vuetify의 i18n 패턴에서 영감:
- Vuetify.lang.current에서 자동으로 현재 언어를 감지
- 언어별 번역 사전을 분리 관리
- 폴백(fallback) 언어 지원
- 확장 가능한 번역 키 시스템

이를 Ssak-Ai에 적용:
- 에이전트 시스템 메시지의 다국어 지원
- 도구 설명/에러 메시지의 자동 번역
- 사용자 언어 자동 감지 및 전환
"""

import locale
import logging

logger = logging.getLogger(__name__)


# ─────────────────── 번역 사전 ───────────────────

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "ko": {
        # 에이전트
        "agent.greeting": "안녕하세요! {agent_name} 에이전트입니다. 무엇을 도와드릴까요?",
        "agent.task_complete": "작업이 완료되었습니다.",
        "agent.task_failed": "작업 중 오류가 발생했습니다: {error}",
        "agent.thinking": "생각 중입니다...",
        "agent.delegating": "{target_agent}에게 작업을 위임합니다.",
        "agent.waiting": "처리 중입니다. 잠시만 기다려주세요...",
        "agent.cancelled": "작업이 취소되었습니다.",
        "agent.tool_using": "도구를 사용하여 작업을 처리 중입니다.",
        # 도구
        "tool.execution_start": "도구 '{tool_name}' 실행 중...",
        "tool.execution_success": "도구 '{tool_name}' 실행 완료.",
        "tool.execution_error": "도구 '{tool_name}' 실행 오류: {error}",
        "tool.hitl_required": "[승인 필요] 에이전트가 다음 작업을 실행하려 합니다: {action}",
        "tool.hitl_approved": "사용자가 승인했습니다.",
        "tool.hitl_denied": "사용자가 거부했습니다.",
        "tool.timeout": "도구 '{tool_name}' 실행 시간이 초과되었습니다.",
        "tool.not_found": "도구 '{tool_name}'을(를) 찾을 수 없습니다.",
        # 보안
        "security.scan_passed": "보안 검사 통과.",
        "security.scan_failed": "보안 위험이 감지되었습니다: {details}",
        "security.access_denied": "접근이 거부되었습니다. PIN 인증이 필요합니다.",
        "security.token_expired": "토큰이 만료되었습니다. 다시 로그인해주세요.",
        "security.rate_limited": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
        # 스킬
        "skill.loaded": "스킬 '{skill_name}' 로드 완료 (도구: {tools})",
        "skill.not_found": "스킬 '{skill_name}'을(를) 찾을 수 없습니다.",
        "skill.install_start": "스킬 '{skill_name}' 설치 중...",
        "skill.install_complete": "스킬 '{skill_name}' 설치 완료.",
        "skill.install_failed": "스킬 '{skill_name}' 설치 실패: {error}",
        "skill.update_available": "스킬 '{skill_name}' 업데이트 가능 (v{version})",
        # 레지스트리
        "registry.summary": "등록된 도구: {count}개",
        "registry.no_tools": "등록된 도구가 없습니다.",
        "registry.loading": "도구 목록을 불러오는 중...",
        # 검색
        "search.starting": "검색을 시작합니다...",
        "search.complete": "검색 완료: {count}개 결과",
        "search.no_results": "'{query}' 검색 결과가 없습니다.",
        "search.error": "검색 중 오류가 발생했습니다: {error}",
        # 시스템
        "system.startup": "Ssak-Ai 시스템을 시작합니다...",
        "system.shutdown": "시스템을 종료합니다.",
        "system.ready": "시스템 준비 완료.",
        "system.restarting": "시스템을 재시작합니다...",
        "system.memory_warning": "메모리 사용량이 높습니다: {usage}%",
        "system.update_available": "새 버전(v{version})이 출시되었습니다.",
        # 채팅
        "chat.welcome": "무엇을 도와드릴까요?",
        "chat.placeholder": "명령어나 질문을 입력하세요...",
        "chat.send": "전송",
        "chat.stop": "중단",
        "chat.clear": "대화 지우기",
        "chat.history": "대화 기록",
        "chat.model_select": "모델 선택",
        # 파일
        "file.read_error": "파일을 읽을 수 없습니다: {path}",
        "file.write_success": "파일 저장 완료: {path}",
        "file.write_error": "파일 저장 실패: {path}",
        "file.not_found": "파일을 찾을 수 없습니다: {path}",
        "file.tree_loading": "파일 트리를 불러오는 중...",
        # 에러
        "error.generic": "오류가 발생했습니다: {message}",
        "error.network": "네트워크 연결을 확인해주세요.",
        "error.server": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        "error.timeout": "요청 시간이 초과되었습니다.",
        "error.unknown": "알 수 없는 오류가 발생했습니다.",
        # UI
        "ui.cancel": "취소",
        "ui.confirm": "확인",
        "ui.save": "저장",
        "ui.loading": "로딩 중...",
        "ui.retry": "재시도",
        "ui.close": "닫기",
        "ui.search": "검색",
        "ui.filter": "필터",
        "ui.refresh": "새로고침",
        "ui.more": "더 보기",
        "ui.less": "접기",
        "ui.copy": "복사",
        "ui.copied": "복사됨",
        "ui.no_data": "데이터가 없습니다.",
        "ui.page_not_found": "페이지를 찾을 수 없습니다.",
    },
    "en": {
        # Agent
        "agent.greeting": "Hello! I'm the {agent_name} agent. How can I help you?",
        "agent.task_complete": "Task completed successfully.",
        "agent.task_failed": "An error occurred during the task: {error}",
        "agent.thinking": "Thinking...",
        "agent.delegating": "Delegating task to {target_agent}.",
        "agent.waiting": "Processing your request. Please wait...",
        "agent.cancelled": "Task was cancelled.",
        "agent.tool_using": "Processing using tools.",
        # Tool
        "tool.execution_start": "Executing tool '{tool_name}'...",
        "tool.execution_success": "Tool '{tool_name}' executed successfully.",
        "tool.execution_error": "Tool '{tool_name}' execution error: {error}",
        "tool.hitl_required": "[Approval Required] Agent wants to execute: {action}",
        "tool.hitl_approved": "User approved.",
        "tool.hitl_denied": "User denied.",
        "tool.timeout": "Tool '{tool_name}' execution timed out.",
        "tool.not_found": "Tool '{tool_name}' not found.",
        # Security
        "security.scan_passed": "Security scan passed.",
        "security.scan_failed": "Security risk detected: {details}",
        "security.access_denied": "Access denied. PIN authentication required.",
        "security.token_expired": "Token expired. Please log in again.",
        "security.rate_limited": "Too many requests. Please try again later.",
        # Skill
        "skill.loaded": "Skill '{skill_name}' loaded (tools: {tools})",
        "skill.not_found": "Skill '{skill_name}' not found.",
        "skill.install_start": "Installing skill '{skill_name}'...",
        "skill.install_complete": "Skill '{skill_name}' installed.",
        "skill.install_failed": "Skill '{skill_name}' installation failed: {error}",
        "skill.update_available": "Update available for '{skill_name}' (v{version})",
        # Registry
        "registry.summary": "Registered tools: {count}",
        "registry.no_tools": "No tools registered.",
        "registry.loading": "Loading tools...",
        # Search
        "search.starting": "Starting search...",
        "search.complete": "Search complete: {count} results",
        "search.no_results": "No results found for '{query}'.",
        "search.error": "Search error: {error}",
        # System
        "system.startup": "Starting Ssak-Ai system...",
        "system.shutdown": "Shutting down system.",
        "system.ready": "System ready.",
        "system.restarting": "Restarting system...",
        "system.memory_warning": "High memory usage: {usage}%",
        "system.update_available": "New version (v{version}) is available.",
        # Chat
        "chat.welcome": "How can I help you?",
        "chat.placeholder": "Type a command or question...",
        "chat.send": "Send",
        "chat.stop": "Stop",
        "chat.clear": "Clear chat",
        "chat.history": "Chat history",
        "chat.model_select": "Select model",
        # File
        "file.read_error": "Cannot read file: {path}",
        "file.write_success": "File saved: {path}",
        "file.write_error": "Failed to save file: {path}",
        "file.not_found": "File not found: {path}",
        "file.tree_loading": "Loading file tree...",
        # Error
        "error.generic": "An error occurred: {message}",
        "error.network": "Please check your network connection.",
        "error.server": "Server error. Please try again later.",
        "error.timeout": "Request timed out.",
        "error.unknown": "An unknown error occurred.",
        # UI
        "ui.cancel": "Cancel",
        "ui.confirm": "Confirm",
        "ui.save": "Save",
        "ui.loading": "Loading...",
        "ui.retry": "Retry",
        "ui.close": "Close",
        "ui.search": "Search",
        "ui.filter": "Filter",
        "ui.refresh": "Refresh",
        "ui.more": "Show more",
        "ui.less": "Show less",
        "ui.copy": "Copy",
        "ui.copied": "Copied",
        "ui.no_data": "No data available.",
        "ui.page_not_found": "Page not found.",
    },
    "ja": {
        # Agent
        "agent.greeting": "こんにちは！{agent_name}エージェントです。何かお手伝いしましょうか？",
        "agent.task_complete": "タスクが完了しました。",
        "agent.task_failed": "タスク中にエラーが発生しました: {error}",
        "agent.thinking": "考え中です...",
        "agent.delegating": "{target_agent}にタスクを委任します。",
        "agent.waiting": "処理中です。お待ちください...",
        "agent.cancelled": "タスクがキャンセルされました。",
        "agent.tool_using": "ツールを使用して処理しています。",
        # Tool
        "tool.execution_start": "ツール '{tool_name}' を実行中...",
        "tool.execution_success": "ツール '{tool_name}' の実行が完了しました。",
        "tool.execution_error": "ツール '{tool_name}' 実行エラー: {error}",
        "tool.hitl_required": "[承認が必要] エージェントが次の操作を実行しようとしています: {action}",
        "tool.hitl_approved": "ユーザーが承認しました。",
        "tool.hitl_denied": "ユーザーが拒否しました。",
        "tool.timeout": "ツール '{tool_name}' の実行がタイムアウトしました。",
        "tool.not_found": "ツール '{tool_name}' が見つかりません。",
        # Security
        "security.scan_passed": "セキュリティスキャンに合格しました。",
        "security.scan_failed": "セキュリティリスクが検出されました: {details}",
        "security.access_denied": "アクセスが拒否されました。PIN認証が必要です。",
        "security.token_expired": "トークンの有効期限が切れました。再ログインしてください。",
        "security.rate_limited": "リクエストが多すぎます。しばらくしてから再試行してください。",
        # Skill
        "skill.loaded": "スキル '{skill_name}' ロード完了 (ツール: {tools})",
        "skill.not_found": "スキル '{skill_name}' が見つかりません。",
        "skill.install_start": "スキル '{skill_name}' インストール中...",
        "skill.install_complete": "スキル '{skill_name}' がインストールされました。",
        "skill.install_failed": "スキル '{skill_name}' インストールに失敗しました: {error}",
        "skill.update_available": "スキル '{skill_name}' のアップデートがあります (v{version})",
        # Registry
        "registry.summary": "登録済みツール: {count}個",
        "registry.no_tools": "登録されたツールはありません。",
        "registry.loading": "ツール一覧を読み込み中...",
        # Search
        "search.starting": "検索を開始します...",
        "search.complete": "検索完了: {count}件の結果",
        "search.no_results": "'{query}' の検索結果はありません。",
        "search.error": "検索エラー: {error}",
        # System
        "system.startup": "Ssak-Ai システムを起動中...",
        "system.shutdown": "システムをシャットダウンします。",
        "system.ready": "システム準備完了。",
        "system.restarting": "システムを再起動中...",
        "system.memory_warning": "メモリ使用量が高いです: {usage}%",
        "system.update_available": "新しいバージョン (v{version}) が利用可能です。",
        # Chat
        "chat.welcome": "何をお手伝いしましょうか？",
        "chat.placeholder": "コマンドや質問を入力してください...",
        "chat.send": "送信",
        "chat.stop": "停止",
        "chat.clear": "会話をクリア",
        "chat.history": "会話履歴",
        "chat.model_select": "モデル選択",
        # File
        "file.read_error": "ファイルを読み込めません: {path}",
        "file.write_success": "ファイルを保存しました: {path}",
        "file.write_error": "ファイルの保存に失敗しました: {path}",
        "file.not_found": "ファイルが見つかりません: {path}",
        "file.tree_loading": "ファイルツリーを読み込み中...",
        # Error
        "error.generic": "エラーが発生しました: {message}",
        "error.network": "ネットワーク接続を確認してください。",
        "error.server": "サーバーエラーが発生しました。後でもう一度お試しください。",
        "error.timeout": "リクエストがタイムアウトしました。",
        "error.unknown": "不明なエラーが発生しました。",
        # UI
        "ui.cancel": "キャンセル",
        "ui.confirm": "確認",
        "ui.save": "保存",
        "ui.loading": "読み込み中...",
        "ui.retry": "再試行",
        "ui.close": "閉じる",
        "ui.search": "検索",
        "ui.filter": "フィルター",
        "ui.refresh": "更新",
        "ui.more": "もっと見る",
        "ui.less": "閉じる",
        "ui.copy": "コピー",
        "ui.copied": "コピーしました",
        "ui.no_data": "データがありません。",
        "ui.page_not_found": "ページが見つかりません。",
    },
}

# 기본 폴백 언어
_DEFAULT_LOCALE = "ko"
_FALLBACK_LOCALE = "en"


class I18n:
    """에이전트 시스템의 다국어 관리자.

    tiptap-vuetify가 Vuetify.lang.current를 자동 감지하듯,
    OS 로케일에서 언어를 자동 감지하거나 명시적으로 설정할 수 있습니다.

    사용 예:
        i18n = I18n()                          # 자동 감지
        i18n = I18n(locale="en")               # 명시 지정
        msg = i18n.t("agent.greeting", agent_name="PM")
    """

    def __init__(self, locale_code: str | None = None):
        """Initialize the I18n.

        Args:
            locale_code (str | None): str | None locale code.

        """
        self._locale: str
        if locale_code:
            if locale_code in _TRANSLATIONS:
                self._locale = locale_code
            else:
                logger.warning(
                    "Locale '%s' not supported. Using fallback: %s",
                    locale_code,
                    _FALLBACK_LOCALE,
                )
                self._locale = _FALLBACK_LOCALE
        else:
            self._locale = self._detect_locale()

        logger.info("I18n initialized with locale: %s", self._locale)

    @property
    def locale(self) -> str:
        """Locale.

        Returns:
            str: The str result.

        """
        return self._locale

    @locale.setter
    def locale(self, value: str):
        if value not in _TRANSLATIONS:
            logger.warning(
                "Locale '%s' not supported. Available: %s. Using fallback: %s",
                value,
                list(_TRANSLATIONS.keys()),
                _FALLBACK_LOCALE,
            )
            self._locale = _FALLBACK_LOCALE
        else:
            self._locale = value
            logger.info("Locale changed to: %s", value)

    def t(self, key: str, **kwargs: object) -> str:
        """번역 키에 대응하는 메시지를 반환합니다.

        tiptap-vuetify의 i18n 맵핑과 동일한 패턴:
        키 → 현재 언어 사전에서 조회 → 없으면 폴백 → 없으면 키 자체 반환

        Args:
            key: 번역 키 (예: "agent.greeting")
            **kwargs: 문자열 포맷 파라미터

        Returns:
            번역된 문자열

        """
        # 1차: 현재 로케일에서 검색
        message = _TRANSLATIONS.get(self._locale, {}).get(key)

        # 2차: 폴백 로케일에서 검색
        if message is None and self._locale != _FALLBACK_LOCALE:
            message = _TRANSLATIONS.get(_FALLBACK_LOCALE, {}).get(key)

        # 3차: 키 자체를 반환
        if message is None:
            logger.debug("Translation not found for key: '%s' (locale=%s)", key, self._locale)
            return key

        # 포맷 파라미터 적용
        try:
            return message.format(**kwargs)
        except (KeyError, IndexError):
            return message

    def add_translations(self, locale_code: str, translations: dict[str, str]):
        """동적으로 번역을 추가합니다.

        tiptap-vuetify의 커스텀 아이콘 팩 확장과 유사하게,
        사용자가 커스텀 번역을 추가/오버라이드할 수 있습니다.
        """
        if locale_code not in _TRANSLATIONS:
            _TRANSLATIONS[locale_code] = {}
        _TRANSLATIONS[locale_code].update(translations)
        logger.info("Added %s translations for locale '%s'", len(translations), locale_code)

    def available_locales(self) -> list[str]:
        """사용 가능한 언어 목록."""
        return list(_TRANSLATIONS.keys())

    def _detect_locale(self) -> str:
        """OS 로케일에서 언어를 자동 감지합니다.

        tiptap-vuetify가 Vuetify.lang.current를 읽는 것과 동일한 원리.
        """
        try:
            os_locale = locale.getlocale()[0]  # 예: "ko_KR" 또는 "Korean_Korea"
            if os_locale:
                lang = os_locale.split("_")[0].lower()  # "ko"
                if lang in _TRANSLATIONS:
                    return lang
        except Exception:
            logger.exception("Unhandled exception")
            pass

        return _DEFAULT_LOCALE

    def summary(self) -> dict[str, object]:
        """현재 i18n 상태 요약."""
        return {
            "current_locale": self._locale,
            "available_locales": self.available_locales(),
            "total_keys": {loc: len(trans) for loc, trans in _TRANSLATIONS.items()},
        }


# ─────────────────── 글로벌 인스턴스 ───────────────────
# tiptap-vuetify처럼 import 즉시 사용 가능한 싱글턴

_global_i18n: I18n | None = None


def get_i18n() -> I18n:
    """글로벌 I18n 인스턴스를 반환합니다. 없으면 자동 생성."""
    global _global_i18n
    if _global_i18n is None:
        _global_i18n = I18n()
    return _global_i18n


def set_locale(locale_code: str):
    """글로벌 로케일을 변경합니다."""
    get_i18n().locale = locale_code


def t(key: str, **kwargs: object) -> str:
    """글로벌 번역 함수 — 어디서든 바로 호출 가능."""
    return get_i18n().t(key, **kwargs)

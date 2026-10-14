"""Ssak-Ai: 시스템 전체 제어 + 환경 자동 최적화 도구.

======================================================
에이전트가 실행 중인 PC의 시스템 리소스를 모니터링하고 제어하며,
실행 환경을 자동으로 최적화하는 도구입니다.

핵심 원칙:
  - 모든 자율 판단은 **사용자 이익 우선**이어야 합니다.
  - 파괴적 행위(프로세스 종료, 설정 변경)는 반드시 확인 가드를 거칩니다.
  - 환경 최적화는 현재 하드웨어를 감지하고 최적 설정을 자동 적용합니다.
"""

import json
import logging
import os
import platform
import shutil
import subprocess
from typing import Callable, Protocol, TypeAlias, cast, final, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from .egress_policy import safe_urlopen

logger = logging.getLogger(__name__)

JsonMap: TypeAlias = dict[str, object]
ActionHandler: TypeAlias = Callable[..., JsonMap]


class _MemoryLike(Protocol):
    total: int
    available: int
    percent: float


class _DiskLike(Protocol):
    total: int
    free: int
    percent: float


def _as_map(value: object) -> JsonMap:
    if not isinstance(value, dict):
        return {}
    mapping = cast(dict[object, object], value)
    return {str(key): item for key, item in mapping.items()}


def _as_list(value: object) -> list[object]:
    return list(cast(list[object], value)) if isinstance(value, list) else []


def _as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_number(value: object, default: int | float) -> int | float:
    return value if isinstance(value, (int, float)) else default


@final
class SystemControlTool(BaseTool):
    """macOS/Linux/Windows 시스템 전체 제어 도구.

    에이전트가 사용자를 위해 시스템을 자율적으로 관리합니다.
    모든 행위는 사용자 이익 우선 원칙에 따라 판단됩니다.
    """

    category = ToolCategory.COMPUTER_USE
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.HIGH
    icon = "⚙️"
    tags = ["system", "os", "control", "optimize", "environment"]

    def __init__(self):
        """Initialize the SystemControlTool."""
        super().__init__()
        self._name: str = "system_control"
        self._description: str = (
            "Control the operating system: manage apps, check system resources, "
            "optimize environment settings, control clipboard/volume/wifi, "
            "and auto-tune the Ssak-Ai configuration for optimal performance. "
            "Always acts in the user's best interest."
        )
        self._schema: JsonMap = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "get_system_info",  # CPU/메모리/디스크/GPU 정보
                        "get_running_apps",  # 실행 중인 앱 목록
                        "launch_app",  # 앱 실행
                        "kill_app",  # 앱 종료
                        "open_url",  # URL 열기
                        "get_clipboard",  # 클립보드 읽기
                        "set_clipboard",  # 클립보드 쓰기
                        "set_volume",  # 볼륨 조절
                        "toggle_wifi",  # WiFi on/off
                        "manage_notifications",  # 방해금지 모드
                        "auto_optimize",  # 환경 자동 최적화
                        "get_env_status",  # 현재 환경 상태 조회
                    ],
                    "description": "The system action to perform.",
                },
                "target": {
                    "type": "string",
                    "description": "Target for the action (app name, URL, text, etc.)",
                },
                "value": {
                    "type": "string",
                    "description": "Value for the action (volume level 0-100, on/off, etc.)",
                },
            },
            "required": ["action"],
        }

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return self._name

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return self._description

    @property
    @override
    def parameters_schema(self) -> JsonMap:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> JsonMap:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        raw_action = kwargs.get("action")
        action = raw_action if isinstance(raw_action, str) else ""
        raw_target = kwargs.get("target", "")
        target = raw_target if isinstance(raw_target, str) else ""
        raw_value = kwargs.get("value", "")
        value = raw_value if isinstance(raw_value, str) else ""

        if not action:
            return {"error": "No action specified."}

        handlers: dict[str, ActionHandler] = {
            "get_system_info": self._action_get_system_info,
            "get_running_apps": self._action_get_running_apps,
            "launch_app": self._action_launch_app,
            "kill_app": self._action_kill_app,
            "open_url": self._action_open_url,
            "get_clipboard": self._action_get_clipboard,
            "set_clipboard": self._action_set_clipboard,
            "set_volume": self._action_set_volume,
            "toggle_wifi": self._action_toggle_wifi,
            "manage_notifications": self._action_manage_notifications,
            "auto_optimize": self._action_auto_optimize,
            "get_env_status": self._action_get_env_status,
        }
        handler = handlers.get(action)
        if handler is None:
            return {"error": f"Unknown action: {action}"}

        try:
            return handler(target=target, value=value)
        except Exception as e:
            logger.error("System control error [%s]: %s", action, e, exc_info=True)
            return {"error": f"Failed to execute '{action}': {str(e)}"}

    # ────────────── 시스템 정보 ──────────────

    def _action_get_system_info(self, **_kwargs: object) -> JsonMap:
        """CPU, 메모리, 디스크, GPU 등 시스템 정보를 수집합니다."""
        info: JsonMap = {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
        }

        # CPU 정보
        try:
            cpu_count = os.cpu_count()
            info["cpu_cores"] = cpu_count
        except Exception:
            logger.exception("Unhandled exception")
            pass

        # 메모리 정보
        try:
            import psutil

            mem = cast(_MemoryLike, cast(object, psutil.virtual_memory()))
            info["memory"] = {
                "total_gb": round(mem.total / (1024**3), 1),
                "available_gb": round(mem.available / (1024**3), 1),
                "used_percent": mem.percent,
            }
            # 디스크 정보
            disk = cast(_DiskLike, cast(object, psutil.disk_usage("/")))
            info["disk"] = {
                "total_gb": round(disk.total / (1024**3), 1),
                "free_gb": round(disk.free / (1024**3), 1),
                "used_percent": round(disk.percent, 1),
            }
        except ImportError:
            # psutil 없으면 시스템 명령으로 대체
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    total_bytes = int(result.stdout.strip())
                    info["memory"] = {"total_gb": round(total_bytes / (1024**3), 1)}
            except Exception:
                logger.exception("Unhandled exception")
                pass

        # GPU 정보 (macOS)
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType", "-json"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    gpu_data = _as_map(cast(object, json.loads(result.stdout)))
                    displays = _as_list(gpu_data.get("SPDisplaysDataType"))
                    if displays:
                        gpu = _as_map(displays[0])
                        info["gpu"] = {
                            "name": gpu.get("sppci_model", "Unknown"),
                            "vram": gpu.get("spdisplays_vram", "Unknown"),
                            "metal_support": gpu.get("sppci_metal", "Unknown"),
                        }
            except Exception:
                logger.exception("Unhandled exception")
                pass

        # Ollama 모델 상태
        try:
            import urllib.request

            req = urllib.request.Request("http://localhost:11434/api/tags")
            with safe_urlopen(req, timeout=5) as resp:
                models = _as_map(cast(object, json.loads(resp.read().decode("utf-8"))))
                info["ollama_models"] = [
                    {
                        "name": _as_str(_as_map(model).get("name")),
                        "size_gb": round(_as_number(_as_map(model).get("size"), 0) / (1024**3), 1),
                    }
                    for model in _as_list(models.get("models"))
                ]
        except Exception:
            logger.exception("Unhandled exception")
            info["ollama_models"] = "Not available"

        return {"status": "ok", "system_info": info}

    def _action_get_env_status(self, **_kwargs: object) -> JsonMap:
        """현재 Ssak-Ai 환경 설정 상태를 조회합니다."""
        config_path = self._find_config_path()
        status: JsonMap = {"config_path": config_path, "settings": {}}

        if config_path and os.path.exists(config_path):
            import yaml

            try:
                with open(config_path, encoding="utf-8") as f:
                    config = _as_map(cast(object, yaml.safe_load(f) or {}))
                status["settings"] = config
            except Exception as e:
                logger.exception("Unhandled exception")
                status["error"] = str(e)

        return {"status": "ok", "env_status": status}

    # ────────────── 앱 관리 ──────────────

    def _action_get_running_apps(self, **_kwargs: object) -> JsonMap:
        """실행 중인 앱 목록을 반환합니다."""
        apps: list[str] = []
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to get name of every process whose background only is false',
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    apps = [a.strip() for a in result.stdout.strip().split(",")]
            except Exception:
                logger.exception("Unhandled exception")
                pass
        else:
            try:
                import psutil

                for proc in psutil.process_iter(["pid", "name"]):
                    name = _as_map(cast(object, proc.info)).get("name")
                    if isinstance(name, str):
                        apps.append(name)
                apps = list(set(apps))[:50]
            except ImportError:
                logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)

        return {"status": "ok", "running_apps": sorted(apps)}

    def _action_launch_app(self, target: str = "", **_kwargs: object) -> JsonMap:
        """앱을 실행합니다."""
        if not target:
            return {"error": "No app name specified."}

        if platform.system() == "Darwin":
            try:
                _ = subprocess.Popen(["open", "-a", target])
                return {"status": "ok", "action": "launch_app", "app": target}
            except Exception as e:
                logger.exception("Unhandled exception")
                return {"error": f"Failed to launch '{target}': {e}"}
        else:
            return {"error": f"App launch not supported on {platform.system()}"}

    def _action_kill_app(self, target: str = "", **_kwargs: object) -> JsonMap:
        """앱을 종료합니다. 사용자 이익 보호: 시스템 핵심 프로세스는 차단됩니다."""
        if not target:
            return {"error": "No app name specified."}

        # 사용자 이익 보호: 핵심 프로세스 종료 차단
        protected = {
            "finder",
            "dock",
            "systemuiserver",
            "loginwindow",
            "kernel_task",
            "launchd",
            "windowserver",
        }
        if target.lower() in protected:
            return {
                "error": f"'{target}' is a protected system process. Killing it would harm the user experience.",
            }

        if platform.system() == "Darwin":
            try:
                _ = subprocess.run(
                    ["osascript", "-e", f'tell application "{target}" to quit'],
                    timeout=10,
                )
                return {"status": "ok", "action": "kill_app", "app": target}
            except Exception as e:
                logger.exception("Unhandled exception")
                return {"error": f"Failed to quit '{target}': {e}"}
        else:
            return {"error": f"App management not supported on {platform.system()}"}

    def _action_open_url(self, target: str = "", **_kwargs: object) -> JsonMap:
        """기본 브라우저에서 URL을 엽니다."""
        if not target:
            return {"error": "No URL specified."}
        try:
            _ = subprocess.Popen(
                ["open", target] if platform.system() == "Darwin" else ["xdg-open", target],
            )
            return {"status": "ok", "action": "open_url", "url": target}
        except Exception as e:
            logger.exception("Unhandled exception")
            return {"error": f"Failed to open URL: {e}"}

    # ────────────── 클립보드 ──────────────

    def _action_get_clipboard(self, **_kwargs: object) -> JsonMap:
        """클립보드 내용을 읽습니다."""
        try:
            if platform.system() == "Darwin":
                result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
                return {"status": "ok", "clipboard": result.stdout}
            else:
                return {"error": f"Clipboard not supported on {platform.system()}"}
        except Exception as e:
            logger.exception("Unhandled exception")
            return {"error": f"Clipboard read failed: {e}"}

    def _action_set_clipboard(self, target: str = "", **_kwargs: object) -> JsonMap:
        """클립보드에 텍스트를 설정합니다."""
        if not target:
            return {"error": "No text specified."}
        try:
            if platform.system() == "Darwin":
                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                _ = process.communicate(target.encode("utf-8"))
                return {
                    "status": "ok",
                    "action": "set_clipboard",
                    "length": len(target),
                }
            else:
                return {"error": f"Clipboard not supported on {platform.system()}"}
        except Exception as e:
            logger.exception("Unhandled exception")
            return {"error": f"Clipboard write failed: {e}"}

    # ────────────── 시스템 설정 ──────────────

    def _action_set_volume(self, value: str = "", **_kwargs: object) -> JsonMap:
        """볼륨을 조절합니다 (0-100)."""
        try:
            level = int(value) if value else 50
            level = max(0, min(100, level))
            if platform.system() == "Darwin":
                _ = subprocess.run(["osascript", "-e", f"set volume output volume {level}"], timeout=5)
                return {"status": "ok", "action": "set_volume", "level": level}
            return {"error": f"Volume control not supported on {platform.system()}"}
        except Exception as e:
            logger.exception("Unhandled exception")
            return {"error": f"Volume control failed: {e}"}

    def _action_toggle_wifi(self, value: str = "", **_kwargs: object) -> JsonMap:
        """WiFi를 켜거나 끕니다."""
        if platform.system() != "Darwin":
            return {"error": f"WiFi control not supported on {platform.system()}"}
        try:
            state = "on" if value.lower() in ("on", "true", "1", "") else "off"
            _ = subprocess.run(["networksetup", "-setairportpower", "en0", state], timeout=10)
            return {"status": "ok", "action": "toggle_wifi", "state": state}
        except Exception as e:
            logger.exception("Unhandled exception")
            return {"error": f"WiFi toggle failed: {e}"}

    def _action_manage_notifications(self, value: str = "", **_kwargs: object) -> JsonMap:
        """방해금지 모드를 토글합니다."""
        if platform.system() != "Darwin":
            return {"error": f"Notification control not supported on {platform.system()}"}
        try:
            # macOS Focus 모드 토글 (Ventura+)
            if value.lower() in ("on", "dnd", "focus"):
                _ = subprocess.run(
                    ["shortcuts", "run", "Turn On Do Not Disturb"],
                    timeout=10,
                    capture_output=True,
                )
                return {"status": "ok", "action": "dnd_on"}
            else:
                _ = subprocess.run(
                    ["shortcuts", "run", "Turn Off Do Not Disturb"],
                    timeout=10,
                    capture_output=True,
                )
                return {"status": "ok", "action": "dnd_off"}
        except Exception as e:
            logger.exception("Unhandled exception")
            return {"error": f"Notification control failed: {e}"}

    # ────────────── 환경 자동 최적화 (사용자 피드백 반영) ──────────────

    def _action_auto_optimize(self, **_kwargs: object) -> JsonMap:
        """시스템 리소스를 감지하고 Ssak-Ai config.yaml을 자동 최적화합니다.

        사용자 이익 원칙:
          - 현재 하드웨어에 맞는 최적 모델/컨텍스트 설정 자동 선택
          - VRAM에 맞는 모델 크기 추천
          - GPU 활용 최적화 (MPS/CUDA)
          - 네트워크 타임아웃 최적화
        """
        import yaml

        # 1. 시스템 정보 수집
        sys_info = _as_map(self._action_get_system_info().get("system_info"))

        # 2. 최적 설정 계산
        optimizations: list[str] = []
        recommended: JsonMap = {}

        # 메모리 기반 컨텍스트 크기 결정
        total_mem = _as_number(_as_map(sys_info.get("memory")).get("total_gb"), 8)
        if total_mem >= 128:
            recommended["context_window"] = 32768
            recommended["max_model_size"] = "70B"
            optimizations.append(f"✅ 충분한 메모리 ({total_mem}GB) → 컨텍스트 32K, 70B 모델 지원")
        elif total_mem >= 64:
            recommended["context_window"] = 16384
            recommended["max_model_size"] = "32B"
            optimizations.append(f"✅ 메모리 {total_mem}GB → 컨텍스트 16K, 32B 모델 권장")
        elif total_mem >= 32:
            recommended["context_window"] = 8192
            recommended["max_model_size"] = "14B"
            optimizations.append(f"⚠️ 메모리 {total_mem}GB → 컨텍스트 8K, 14B 모델 권장")
        else:
            recommended["context_window"] = 4096
            recommended["max_model_size"] = "7B"
            optimizations.append(f"⚠️ 메모리 {total_mem}GB → 컨텍스트 4K, 7B 이하 모델 권장")

        # GPU 감지
        gpu_info = _as_map(sys_info.get("gpu"))
        gpu_name = _as_str(gpu_info.get("name")).lower()
        if (
            "apple" in gpu_name
            or "m1" in gpu_name
            or "m2" in gpu_name
            or "m3" in gpu_name
            or "m4" in gpu_name
            or "m5" in gpu_name
        ):
            recommended["gpu_acceleration"] = "mps"
            recommended["keep_alive"] = "30m"
            optimizations.append(
                f"✅ Apple Silicon GPU 감지 ({_as_str(gpu_info.get('name'))}) → MPS 가속 활성화",
            )
        elif gpu_info:
            recommended["gpu_acceleration"] = "cuda"
            optimizations.append("✅ NVIDIA GPU 감지 → CUDA 가속 활성화")

        # CPU 코어 기반 병렬 처리
        cpu_cores = int(_as_number(sys_info.get("cpu_cores"), 4))
        recommended["num_parallel"] = min(cpu_cores, 8)
        optimizations.append(f"✅ CPU {cpu_cores}코어 → 병렬 처리 {recommended['num_parallel']}개")

        # Ollama 모델 현황 기반 추천
        ollama_models = _as_list(sys_info.get("ollama_models"))
        if ollama_models:
            model_names = [name for name in (_as_str(_as_map(model).get("name")) for model in ollama_models) if name]
            recommended["available_models"] = model_names
            optimizations.append(
                f"✅ Ollama 모델 {len(model_names)}개 감지: {', '.join(model_names[:5])}",
            )

        # 3. config.yaml 업데이트
        config_path = self._find_config_path()
        config_updated = False

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = _as_map(cast(object, yaml.safe_load(f) or {}))

                # 기존 설정 백업
                backup_path = config_path + ".backup"
                if not os.path.exists(backup_path):
                    _ = shutil.copy2(config_path, backup_path)
                    optimizations.append(f"📋 기존 설정 백업: {backup_path}")

                # 최적 설정 적용
                ollama = _as_map(config.get("ollama"))
                config["ollama"] = ollama
                ollama["context_window"] = recommended.get("context_window", 8192)
                ollama["keep_alive"] = recommended.get("keep_alive", "15m")

                performance = _as_map(config.get("performance"))
                config["performance"] = performance
                performance["num_parallel"] = recommended.get("num_parallel", 4)
                performance["max_model_size"] = recommended.get("max_model_size", "14B")

                if recommended.get("gpu_acceleration"):
                    performance["gpu_acceleration"] = recommended["gpu_acceleration"]

                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

                config_updated = True
                optimizations.append("✅ config.yaml 자동 업데이트 완료")
            except Exception as e:
                logger.exception("Unhandled exception")
                optimizations.append(f"⚠️ config.yaml 업데이트 실패: {e}")

        return {
            "status": "ok",
            "action": "auto_optimize",
            "optimizations": optimizations,
            "recommended": recommended,
            "config_updated": config_updated,
            "message": (
                "🚀 **환경 최적화 완료**\n\n"
                + "\n".join(optimizations)
                + "\n\n모든 설정은 사용자 이익을 최우선으로 최적화되었습니다."
            ),
        }

    # ────────────── 유틸리티 ──────────────

    def _find_config_path(self) -> str | None:
        """config.yaml 경로를 찾습니다."""
        current = os.path.dirname(os.path.abspath(__file__))
        for _ in range(6):
            candidate = os.path.join(current, "config.yaml")
            if os.path.exists(candidate):
                return candidate
            current = os.path.dirname(current)
        return None

"""unsloth_script_api — 생성된 Unsloth 스크립트의 Python API 드리프트 검사 (Phase 53).

mlx-lm 플래그 드리프트 가드(Phase 22, test_mlx_command_flags.py)의 Python API 판.
lora_pipeline이 생성하는 Unsloth 학습 스크립트(train_sft.py/train_dpo.py)는
FastLanguageModel, SFTTrainer/DPOTrainer, TrainingArguments/DPOConfig 등의
시그니처에 의존한다. unsloth/trl은 버전 간 인자 이름을 바꾼 적이 잦고
(예: SFTTrainer의 tokenizer→processing_class, max_seq_length→max_length),
스크립트가 런타임에 실패하면 GPU 서버 사용자만 피해를 본다.

검증 방법:
  1. 생성된 스크립트 소스에서 import/호출/키워드 인자를 AST로 추출
  2. 설치된 unsloth/trl/transformers의 실제 시그니처(inspect.signature)와 대조
  3. 존재하지 않는 이름·알 수 없는 kwargs를 보고 (TRL/draccus kwargs 전파는
     런타임 **kwargs로 흡수되는 경우가 많아 알 수 없는 kwargs는 '알림' 수준)

unsloth/trl 미설치 환경(로컬 macOS 등)에서는 전체 스킵 — guard는 deps=unsloth
환경(CI/GPU)에서 의미가 있다. 실제 모델 로딩은 하지 않으므로 빠르다.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field

# 생성 스크립트가 import하는 모듈 → 검사 대상 이름 매핑
_TARGET_MODULES = {
    "unsloth": {"FastLanguageModel", "is_bfloat16_supported"},
    "trl": {"SFTTrainer", "DPOTrainer", "DPOConfig", "TrainingArguments"},
    "transformers": {"TrainingArguments"},
}


@dataclass
class ScriptApiUsage:
    """스크립트 소스에서 추출한 API 사용 내역."""

    imported: dict[str, set[str]] = field(default_factory=dict)
    """module → {names}"""

    calls: dict[str, set[str]] = field(default_factory=dict)
    """qualified name (FastLanguageModel.from_pretrained 등) → 호출됨"""

    kwargs: dict[str, set[str]] = field(default_factory=dict)
    """qualified name → {kwarg names}"""


def extract_script_api(source: str) -> ScriptApiUsage:
    """생성된 스크립트 소스에서 import·호출·kwargs를 AST로 추출한다."""
    usage = ScriptApiUsage()
    tree = ast.parse(source)

    # import 별칭 해소: SFTTrainer(...) 같은 이름이 어떤 모듈에서 왔는지
    name_to_module: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _TARGET_MODULES:
            for alias in node.names:
                name_to_module[alias.asname or alias.name] = node.module
                usage.imported.setdefault(node.module, set()).add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _TARGET_MODULES:
                    name_to_module[alias.asname or alias.name.split(".")[0]] = alias.name

    def _resolve(call: ast.Call) -> str:
        """호출명을 'module.Class.method' 형태로 해소.

        FastLanguageModel.from_pretrained(...)은 'unsloth.FastLanguageModel.from_pretrained'로
        해소돼야지 'unsloth.from_pretrained'가 되면 안 된다 — 검증 대상이 클래스 메서드이므로.
        """
        func = call.func
        if isinstance(func, ast.Name):
            module = name_to_module.get(func.id)
            return f"{module}.{func.id}" if module else func.id
        if isinstance(func, ast.Attribute):
            # 체인의 루트 Name을 찾아 모듈/클래스 해소.
            # import된 이름(FastLanguageModel 등)은 루트에서 멈춘다 — 'FastLanguageModel.from_pretrained'는
            # 'unsloth.FastLanguageModel.from_pretrained' (모듈 메서드 아닌 클래스 메서드).
            parts: list[str] = [func.attr]
            cursor: ast.expr = func.value
            while isinstance(cursor, ast.Attribute):
                parts.append(cursor.attr)
                cursor = cursor.value
            if isinstance(cursor, ast.Name):
                root = cursor.id
                module = name_to_module.get(root)
                parts.append(root)
                if module and module != root:
                    parts.append(module)
                return ".".join(reversed(parts))
        return ""

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        qualname = _resolve(node)
        if not qualname:
            continue
        usage.calls.setdefault(qualname, set())
        for kw in node.keywords:
            if kw.arg:
                usage.kwargs.setdefault(qualname, set()).add(kw.arg)
    return usage


def _signature_kwargs(obj: object) -> tuple[set[str], bool]:
    """객체가 받을 수 있는 kwargs 집합. **kwargs 전파 시 (set(), True)."""
    if not callable(obj):
        return set(), True
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return set(), True
    kwargs: set[str] = set()
    has_var_kw = False
    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            has_var_kw = True
        elif param.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            kwargs.add(param.name)
    return kwargs, has_var_kw


def verify_against_installed(usage: ScriptApiUsage) -> tuple[list[str], list[str]]:
    """설치된 라이브러리 시그니처와 대조. (errors, warnings) 반환.

    errors: 존재하지 않는 import/메서드 — 스크립트가 즉시 실패
    warnings: 시그니처에 없는 kwargs — **kwargs 흡수 여부를 몰라 알림 수준
    """
    errors: list[str] = []
    warnings: list[str] = []

    modules = {}
    for module_name in usage.imported:
        try:
            modules[module_name] = __import__(module_name)
        except ImportError as exc:
            errors.append(f"모듈 미설치: {module_name} ({exc})")
            continue

    for module_name, names in usage.imported.items():
        module = modules.get(module_name)
        if module is None:
            continue
        for name in names:
            if not hasattr(module, name):
                errors.append(f"{module_name}.{name} 이(가) 설치된 {module_name}에 없음 — 스크립트 import 실패")

    for qualname, _ in usage.calls.items():
        if "." not in qualname:
            continue
        module_name, _, attr_path = qualname.partition(".")
        module = modules.get(module_name)
        if module is None:
            continue
        # attr_path의 첫 세그먼트는 import된 이름(클래스/함수) — 순서대로 속성 접근
        obj: object = module
        for part in attr_path.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                break
        if obj is None:
            errors.append(f"{qualname} 이(가) 설치된 {module_name}에 없음 — 스크립트 실행 실패")
            continue

        valid, has_var_kw = _signature_kwargs(obj)
        used = usage.kwargs.get(qualname, set())
        unknown = used - valid
        if unknown and not has_var_kw:
            warnings.append(f"{qualname}: 알 수 없는 kwargs {sorted(unknown)} — 설치된 시그니처에 없음 (드리프트 의심)")
        elif unknown:
            warnings.append(
                f"{qualname}: 시그니처에 명시 없는 kwargs {sorted(unknown)} — **kwargs로 흡수될 수 있음(런타임 확인 불가)",
            )
    return errors, warnings

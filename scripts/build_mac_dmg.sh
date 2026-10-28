#!/usr/bin/env bash
# ==============================================================================
# Ssak-Ai macOS .app 번들 및 .dmg 디스크 이미지 빌더
# ==============================================================================
# 기능:
# 1. 고해상도 앱 아이콘(AppIcon.icns) 자동 생성 (dashboard/public/icon-512.png 기반)
# 2. 독립 실행형 macOS 애플리케이션 번들(Ssak-Ai.app) 구성
# 3. GUI 환경 PATH 확장 및 데몬 자동 구동/헬스체크/브라우저 오픈 런처 탑재
# 4. Applications 심볼릭 링크를 포함한 배포용 압축 .dmg (UDZO) 패키징
# 5. 마운트 무결성 검증 및 SHA-256 체크섬 발행
# ==============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 버전 확인
VERSION="$(python3 -c "
import tomllib
try:
    with open('$ROOT_DIR/pyproject.toml', 'rb') as f:
        data = tomllib.load(f)
    print(data.get('project', {}).get('version') or '0.1.0')
except Exception:
    print('0.1.0')
" 2>/dev/null || echo "0.1.0")"

# 디렉터리 정의
BUILD_DIR="$ROOT_DIR/build/mac"
APP_NAME="Ssak-Ai"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
DMG_STAGE_DIR="$BUILD_DIR/dmg_stage"
DIST_DIR="$ROOT_DIR/dist"
DMG_NAME="Ssak-Ai-$VERSION.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"

echo "============================================================"
echo "▶ Ssak-Ai macOS DMG 빌더 시작 (v$VERSION)"
echo "============================================================"

mkdir -p "$BUILD_DIR" "$DIST_DIR"
rm -rf "$APP_BUNDLE" "$DMG_STAGE_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR" "$DMG_STAGE_DIR"

# 1. AppIcon.icns 생성
SOURCE_ICON="$ROOT_DIR/dashboard/public/icon-512.png"
if [[ -f "$SOURCE_ICON" ]]; then
    echo "▶ 앱 아이콘 생성 중 (AppIcon.icns)..."
    ICONSET_DIR="/tmp/agk_icon_$$.iconset"
    mkdir -p "$ICONSET_DIR"

    sips -z 16 16     "$SOURCE_ICON" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null 2>&1
    sips -z 32 32     "$SOURCE_ICON" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1
    sips -z 32 32     "$SOURCE_ICON" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null 2>&1
    sips -z 64 64     "$SOURCE_ICON" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1
    sips -z 128 128   "$SOURCE_ICON" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null 2>&1
    sips -z 256 256   "$SOURCE_ICON" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1
    sips -z 256 256   "$SOURCE_ICON" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null 2>&1
    sips -z 512 512   "$SOURCE_ICON" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1
    sips -z 512 512   "$SOURCE_ICON" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null 2>&1

    iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES_DIR/AppIcon.icns"
    rm -rf "$ICONSET_DIR"
    echo "  ✓ AppIcon.icns 생성 완료"
fi

# 2. Info.plist 생성
echo "▶ Info.plist 생성 중..."
cat > "$CONTENTS_DIR/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.antigravity.k</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>AGTK</string>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2026 Ssak-Ai. All rights reserved.</string>
</dict>
</plist>
EOF
plutil -lint "$CONTENTS_DIR/Info.plist" >/dev/null
echo "  ✓ Info.plist 검증 완료"

# 3. 런처 스크립트 (Contents/MacOS/Ssak-Ai)
echo "▶ 애플리케이션 런처 스크립트 작성 중..."
cat > "$MACOS_DIR/$APP_NAME" <<'LAUNCHER_EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

# 1. macOS GUI 환경용 PATH 확장
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SERVER_HOST="127.0.0.1"
SERVER_PORT="8000"
SERVER_URL="http://${SERVER_HOST}:${SERVER_PORT}"
LOG_DIR="$HOME/Library/Logs/Ssak-Ai"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/server.log"

# Packaged profile: optional services require an explicit request.
export AGK_IDE_SERVER_AUTOSTART="${AGK_IDE_SERVER_AUTOSTART:-0}"
export AGK_PROJECT_RAG_ENABLED="${AGK_PROJECT_RAG_ENABLED:-false}"

# 2. 이미 실행 중인지 확인
if curl -s -f -m 1 "$SERVER_URL/health" >/dev/null 2>&1 || curl -s -f -m 1 "$SERVER_URL/api/health" >/dev/null 2>&1; then
    osascript -e 'display notification "이미 실행 중인 Ssak-Ai 대시보드를 브라우저에 엽니다." with title "Ssak-Ai"' 2>/dev/null || true
    open "$SERVER_URL"
    exit 0
fi

# 3. 번들 리소스 경로 파악 (Contents/MacOS/../Resources/app)
APP_BUNDLE_ROOT="$(cd "$(dirname "$0")/../Resources/app" 2>/dev/null && pwd || true)"

# 4. 사용자 작업 및 데이터 디렉터리 준비 (읽기 전용 DMG/Applications 탈피)
USER_DATA_DIR="$HOME/.antigravity-k"
mkdir -p "$USER_DATA_DIR/data" "$USER_DATA_DIR/logs" "$USER_DATA_DIR/models"

# 경로 환경변수 export (모든 쓰기 작업을 사용자 홈 디렉터리로 리디렉션)
export AGK_PATH_PROJECT_ROOT="${AGK_PATH_PROJECT_ROOT:-$USER_DATA_DIR}"
export AGK_PATH_DATA_DIR="$USER_DATA_DIR/data"
export AGK_PATH_LOGS_DIR="$LOG_DIR"
export AGK_PATH_MODELS_DIR="$USER_DATA_DIR/models"
export AGK_PATH_DOCUMENTS_DIR="$USER_DATA_DIR/data/documents"
export AGK_PATH_VECTORS_DIR="$USER_DATA_DIR/data/vectors"
export AGK_PATH_WIKI_DIR="$USER_DATA_DIR/data/wiki_entries"
export AGK_TASK_DB_PATH="$USER_DATA_DIR/data/tasks.db"
export AGK_KANBAN_DB_PATH="$USER_DATA_DIR/data/kanban.db"
export AGK_MEMORY_DB_PATH="$USER_DATA_DIR/data/memory.db"

# config.yaml 복사 (사용자 디렉터리에 없으면 번들 기본값 복사)
if [[ ! -f "$USER_DATA_DIR/config.yaml" && -f "$APP_BUNDLE_ROOT/config.yaml" ]]; then
    cp "$APP_BUNDLE_ROOT/config.yaml" "$USER_DATA_DIR/config.yaml"
fi
if [[ -f "$USER_DATA_DIR/config.yaml" ]]; then
    export AGK_CONFIG_FILE="$USER_DATA_DIR/config.yaml"
fi

# 5. PYTHONPATH 설정 (번들된 src 및 site-packages를 최우선으로 주입)
BUNDLED_SP=""
if [[ -d "$APP_BUNDLE_ROOT/site-packages" ]]; then
    BUNDLED_SP=":$APP_BUNDLE_ROOT/site-packages"
fi
if [[ -d "$APP_BUNDLE_ROOT/src" ]]; then
    export PYTHONPATH="$APP_BUNDLE_ROOT/src${BUNDLED_SP}:${PYTHONPATH:-}"
fi

# 6. 실행 Python 바이너리 탐색 (Python >= 3.12 필수)
check_py() {
    local candidate="$1"
    if [[ -n "$candidate" && -x "$candidate" ]]; then
        local ver
        ver="$("$candidate" -c 'import sys; print(sys.version_info[0]*100 + sys.version_info[1])' 2>/dev/null || echo 0)"
        if [[ "$ver" -ge 312 ]]; then
            echo "$candidate"
            return 0
        fi
    fi
    return 1
}

PY_BIN=""
# Prefer in-bundle interpreter (Resources/python) when present (1a incremental).
# Fallback: host search. Fail-closed with alert if none found.
CANDIDATES=(
    "$APP_BUNDLE_ROOT/../python/bin/python3"
    "$APP_BUNDLE_ROOT/../python/bin/python"
    "$APP_BUNDLE_ROOT/../../../../.venv/bin/python"
    "$USER_DATA_DIR/venv/bin/python"
    "$(command -v uv >/dev/null 2>&1 && uv python find 2>/dev/null || true)"
    "$HOME/miniforge3/bin/python3"
    "$HOME/miniforge3/bin/python"
    "$HOME/anaconda3/bin/python3"
    "$(command -v python3.13 || true)"
    "$(command -v python3.12 || true)"
    "/opt/homebrew/bin/python3.13"
    "/opt/homebrew/bin/python3.12"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3.13"
    "/usr/local/bin/python3.12"
    "/usr/local/bin/python3"
    "$(command -v python3 || true)"
    "$(command -v python || true)"
)

for c in "${CANDIDATES[@]}"; do
    [[ -z "$c" ]] && continue
    if PY_BIN="$(check_py "$c")"; then
        break
    fi
done

if [[ -z "$PY_BIN" ]]; then
    osascript -e 'display alert "Ssak-Ai 실행 실패" message "Python 3.12 이상의 런타임을 찾을 수 없습니다.\n\n• 기본 DMG: 호스트에 Python 3.12+ (또는 uv) 설치 필요\n• 동봉 빌드(SSAK_BUNDLE_PYTHON=1): Resources/python 이 있어야 함\n\n터미널에서 uv 또는 Python 3.12+를 설치하거나, 동봉 빌드 DMG를 사용하세요." as critical' 2>/dev/null || true
    exit 1
fi

CMD="$PY_BIN -m antigravity_k.cli serve --host $SERVER_HOST --port $SERVER_PORT"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Ssak-Ai via $PY_BIN: $CMD" >> "$LOG_FILE"

# 백그라운드 서버 실행 (항상 사용자 쓰기 가능 디렉터리에서 실행)
(cd "$USER_DATA_DIR" && nohup $CMD >> "$LOG_FILE" 2>&1 &)

# 7. 헬스체크 대기 (최대 25초)
READY=0
for i in {1..50}; do
    if curl -s -f -m 1 "$SERVER_URL/health" >/dev/null 2>&1 || curl -s -f -m 1 "$SERVER_URL/api/health" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 0.5
done

if [[ "$READY" -eq 1 ]]; then
    osascript -e 'display notification "Ssak-Ai 서버가 준비되었습니다. 대시보드를 엽니다." with title "Ssak-Ai"' 2>/dev/null || true
    open "$SERVER_URL"
else
    ERR_TAIL="$(tail -n 10 "$LOG_FILE" 2>/dev/null | tr '\n' ' ' | cut -c1-150 || echo '')"
    osascript -e "display alert \"서버 시작 실패 또는 응답 지연\" message \"Ssak-Ai 서버가 응답하지 않습니다.\n\n로그 위치: $LOG_FILE\n최근 오류: $ERR_TAIL\" as critical" 2>/dev/null || true
    exit 1
fi
LAUNCHER_EOF

chmod +x "$MACOS_DIR/$APP_NAME"
echo "  ✓ 런처 스크립트 작성 및 실행 권한 부여 완료"

# 4. 소스 및 내장 대시보드 리소스 번들링 (Resources/app)
echo "▶ 애플리케이션 코어 리소스 번들링 중..."
APP_BUNDLE_APP="$RESOURCES_DIR/app"
mkdir -p "$APP_BUNDLE_APP"

# Phase 1 (desktop shell plan): fail-closed dashboard_dist — never ship without SPA.
DASHBOARD_DIST_SRC="$ROOT_DIR/src/antigravity_k/dashboard_dist"
if [[ ! -f "$DASHBOARD_DIST_SRC/index.html" ]]; then
    echo "▶ dashboard_dist 없음 — production 빌드 시도 (pnpm --dir dashboard build)..."
    if command -v pnpm >/dev/null 2>&1; then
        pnpm --dir "$ROOT_DIR/dashboard" build
    else
        echo "ERROR: pnpm 없음. dashboard_dist/index.html 을 먼저 빌드하세요." >&2
        exit 1
    fi
fi
if [[ ! -f "$DASHBOARD_DIST_SRC/index.html" ]]; then
    echo "ERROR: src/antigravity_k/dashboard_dist/index.html 이 없습니다. 번들을 중단합니다." >&2
    exit 1
fi

# 소스코드 및 필수 설정 복사
# 개인사용·모바일 Host 전제: 번들에 비밀(.env/auth_hash)을 넣지 않는다.
# 실제 키/PIN은 사용자 데이터 디렉터리(~/.antigravity-k 등)에만 둔다.
rsync -a --delete   --exclude '.env'   --exclude '.env.*'   --exclude 'auth_hash'   --exclude 'auth_hash.*'   --exclude '__pycache__/'   --exclude '*.pyc'   "$ROOT_DIR/src/" "$APP_BUNDLE_APP/src/"
cp "$ROOT_DIR/pyproject.toml" "$APP_BUNDLE_APP/"
cp "$ROOT_DIR/config.yaml" "$APP_BUNDLE_APP/"
[[ -f "$ROOT_DIR/README.md" ]] && cp "$ROOT_DIR/README.md" "$APP_BUNDLE_APP/"
[[ -f "$ROOT_DIR/LICENSE" ]] && cp "$ROOT_DIR/LICENSE" "$APP_BUNDLE_APP/"
# dist는 명시 동기화(누락 방지)
rm -rf "$APP_BUNDLE_APP/src/antigravity_k/dashboard_dist"
cp -R "$DASHBOARD_DIST_SRC" "$APP_BUNDLE_APP/src/antigravity_k/dashboard_dist"
[[ -f "$ROOT_DIR/uv.lock" ]] && cp "$ROOT_DIR/uv.lock" "$APP_BUNDLE_APP/"

# 방어: 혹시 남은 비밀 후보가 있으면 즉시 실패 (경로는 출력, 내용은 출력하지 않음)
SECRET_HITS="$(find "$APP_BUNDLE_APP" \( -name '.env' -o -name '.env.*' -o -name 'auth_hash' -o -name 'auth_hash.*' \) -type f 2>/dev/null || true)"
if [[ -n "${SECRET_HITS}" ]]; then
    echo "ERROR: 번들에 비밀 후보 파일이 포함되었습니다. 중단합니다." >&2
    echo "${SECRET_HITS}" >&2
    exit 1
fi

# Optional 1a prep: resolve standalone CPython BEFORE site-packages so ABI tags match.
# Default OFF keeps host-Python DMG ~55M; SSAK_BUNDLE_PYTHON=1 embeds interpreter (~50–60M+).
resolve_standalone_cpython() {
    # Prefer uv-managed trees under ~/.local/share/uv/python (not venv→conda).
    local ver cand real prefix share
    share="${UV_PYTHON_INSTALL_DIR:-$HOME/.local/share/uv/python}"
    for ver in 3.12 3.13; do
        # Direct uv share lookup first (uv python find may return project .venv).
        for cand in "$share"/cpython-${ver}-macos-*/bin/python${ver} "$share"/cpython-${ver}.*-macos-*/bin/python${ver}; do
            [[ -x "$cand" ]] || continue
            real="$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$cand" 2>/dev/null || true)"
            [[ -z "$real" ]] && real="$cand"
            prefix="$(cd "$(dirname "$real")/.." && pwd)"
            if [[ -d "$prefix/lib" && -d "$prefix/bin" ]]; then
                echo "$prefix"
                return 0
            fi
        done
        if command -v uv >/dev/null 2>&1; then
            cand="$(uv python find "$ver" 2>/dev/null || true)"
            if [[ -n "$cand" && -x "$cand" ]]; then
                real="$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$cand" 2>/dev/null || true)"
                [[ -z "$real" ]] && real="$cand"
                prefix="$(cd "$(dirname "$real")/.." && pwd)"
                if [[ -d "$prefix/lib" && -d "$prefix/bin" ]]; then
                    if [[ "$prefix" == *"/uv/python/"* ]] || [[ "$prefix" == *"cpython-"* ]]; then
                        echo "$prefix"
                        return 0
                    fi
                fi
            fi
        fi
    done
    return 1
}

BUNDLE_PY_DEST=""
PY_SRC=""
PIP_PYTHON=""
if [[ "${SSAK_BUNDLE_PYTHON:-0}" == "1" ]]; then
    echo "▶ SSAK_BUNDLE_PYTHON=1 — standalone CPython 해석 중 (site-packages ABI 정합)..."
    if ! PY_SRC="$(resolve_standalone_cpython)"; then
        echo "ERROR: SSAK_BUNDLE_PYTHON=1 이지만 복사할 standalone CPython을 찾지 못했습니다." >&2
        echo "  힌트: uv python install 3.12 후 재시도" >&2
        exit 1
    fi
    echo "  → 소스: $PY_SRC"
    if [[ -x "$PY_SRC/bin/python3" ]]; then
        PIP_PYTHON="$PY_SRC/bin/python3"
    elif [[ -x "$PY_SRC/bin/python3.12" ]]; then
        PIP_PYTHON="$PY_SRC/bin/python3.12"
    elif [[ -x "$PY_SRC/bin/python3.13" ]]; then
        PIP_PYTHON="$PY_SRC/bin/python3.13"
    else
        echo "ERROR: standalone prefix 에 python3 실행 파일이 없습니다: $PY_SRC/bin" >&2
        exit 1
    fi
fi

# 필수 의존성 패키지 번들링 (uv.lock 기반 정확한 버전으로 독립 런타임 구성)
echo "▶ 필수 런타임 패키지 번들링 중 (site-packages)..."
mkdir -p "$APP_BUNDLE_APP/site-packages"
if command -v uv >/dev/null 2>&1; then
    TEMP_REQS="/tmp/agk_dmg_reqs_$$.txt"
    uv export --no-dev --no-editable --no-hashes | grep -v "^\." > "$TEMP_REQS"
    # When bundling CPython, install wheels for THAT interpreter (fail-closed ABI match).
    if [[ -n "$PIP_PYTHON" ]]; then
        echo "  → uv pip install --python $PIP_PYTHON (동봉 인터프리터 ABI)"
        uv pip install --python "$PIP_PYTHON" --target "$APP_BUNDLE_APP/site-packages" -r "$TEMP_REQS" >/dev/null 2>&1
    else
        uv pip install --target "$APP_BUNDLE_APP/site-packages" -r "$TEMP_REQS" >/dev/null 2>&1
    fi
    rm -f "$TEMP_REQS"
    echo "  ✓ site-packages 번들링 완료 ($(du -sh "$APP_BUNDLE_APP/site-packages" | cut -f1))"
fi

if [[ "${SSAK_BUNDLE_PYTHON:-0}" == "1" ]]; then
    echo "▶ SSAK_BUNDLE_PYTHON=1 — 동봉 CPython 복사 중 (Resources/python)..."
    BUNDLE_PY_DEST="$RESOURCES_DIR/python"
    rm -rf "$BUNDLE_PY_DEST"
    mkdir -p "$BUNDLE_PY_DEST"
    rsync -a --delete \
        --exclude '__pycache__/' \
        --exclude '*.pyc' \
        --exclude 'share/man/' \
        --exclude 'share/doc/' \
        "$PY_SRC/" "$BUNDLE_PY_DEST/"
    # Ensure python3 exists
    if [[ ! -x "$BUNDLE_PY_DEST/bin/python3" ]]; then
        if [[ -x "$BUNDLE_PY_DEST/bin/python3.12" ]]; then
            ln -sf python3.12 "$BUNDLE_PY_DEST/bin/python3"
        elif [[ -x "$BUNDLE_PY_DEST/bin/python3.13" ]]; then
            ln -sf python3.13 "$BUNDLE_PY_DEST/bin/python3"
        elif [[ -x "$BUNDLE_PY_DEST/bin/python" ]]; then
            ln -sf python "$BUNDLE_PY_DEST/bin/python3"
        else
            echo "ERROR: Resources/python/bin 에 python3 실행 파일이 없습니다." >&2
            exit 1
        fi
    fi
    # Sanity: must be >= 3.12
    BPY_VER="$("$BUNDLE_PY_DEST/bin/python3" -c 'import sys; print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)"
    if [[ "$BPY_VER" -lt 312 ]]; then
        echo "ERROR: 동봉 Python 버전이 3.12 미만입니다 ($BPY_VER)." >&2
        exit 1
    fi
    # Fail-closed ABI: native ext must import under bundled interpreter
    if ! PYTHONPATH="$APP_BUNDLE_APP/site-packages${PYTHONPATH:+:$PYTHONPATH}" \
        "$BUNDLE_PY_DEST/bin/python3" -c 'import pydantic_core' 2>/dev/null; then
        echo "ERROR: 동봉 Python 으로 site-packages(pydantic_core) import 실패 — ABI 불일치." >&2
        echo "  힌트: SSAK_BUNDLE_PYTHON=1 빌드는 동봉 인터프리터로 uv pip install 해야 합니다." >&2
        exit 1
    fi
    echo "  ✓ 동봉 Python 완료 ($(du -sh "$BUNDLE_PY_DEST" | cut -f1)) — DMG 용량이 기본(~55M)보다 커집니다"
    echo "  ✓ ABI 스모크: pydantic_core import OK under Resources/python"
else
    echo "  · SSAK_BUNDLE_PYTHON unset/0 — 호스트 Python 탐색 유지 (기본 DMG ~55M)"
fi

# 불필요한 캐시 파일 정리 및 권한 부여
find "$APP_BUNDLE_APP" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$APP_BUNDLE_APP" -type f -name "*.pyc" -delete 2>/dev/null || true
chmod -R u+rwX,go+rX "$APP_BUNDLE"
echo "  ✓ 번들 리소스 동기화 완료 ($(du -sh "$APP_BUNDLE_APP" | cut -f1))"

# 5. DMG 스테이징 및 패키징
echo "▶ DMG 스테이징 준비 중..."
cp -R "$APP_BUNDLE" "$DMG_STAGE_DIR/"
ln -s /Applications "$DMG_STAGE_DIR/Applications"

rm -f "$DMG_PATH"
echo "▶ hdiutil 기반 압축 디스크 이미지(UDZO) 생성 중..."
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_STAGE_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH" >/dev/null

echo "  ✓ DMG 생성 완료: $DMG_PATH ($(du -sh "$DMG_PATH" | cut -f1))"

# 6. 마운트 검증
echo "▶ 생성된 DMG 마운트 무결성 검증 중..."
MOUNT_POINT="/tmp/agk_dmg_verify_$$"
mkdir -p "$MOUNT_POINT"
hdiutil attach "$DMG_PATH" -mountpoint "$MOUNT_POINT" -nobrowse -readonly >/dev/null

if [[ -d "$MOUNT_POINT/$APP_NAME.app" && -L "$MOUNT_POINT/Applications" ]]; then
    echo "  ✓ 마운트 볼륨 내 Ssak-Ai.app 및 /Applications 심볼릭 링크 정상 확인"
    plutil -lint "$MOUNT_POINT/$APP_NAME.app/Contents/Info.plist" >/dev/null
    echo "  ✓ 볼륨 내 Info.plist 유효성 검증 완료"
fi

hdiutil detach "$MOUNT_POINT" >/dev/null
rm -rf "$MOUNT_POINT"

# 7. 체크섬 생성
DMG_SHA256="$(shasum -a 256 "$DMG_PATH" | cut -d' ' -f1)"
echo "$DMG_SHA256  $DMG_NAME" > "$DIST_DIR/$DMG_NAME.sha256"

echo "============================================================"
echo "🎉 Ssak-Ai macOS .dmg 빌드 성공!"
echo "   - 파일: $DMG_PATH"
echo "   - 용량: $(du -sh "$DMG_PATH" | cut -f1)"
echo "   - SHA-256: $DMG_SHA256"
echo "============================================================"

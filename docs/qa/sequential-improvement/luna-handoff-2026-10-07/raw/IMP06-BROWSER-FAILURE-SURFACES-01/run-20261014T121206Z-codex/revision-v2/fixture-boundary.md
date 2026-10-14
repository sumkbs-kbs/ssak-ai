# v2 입력 격리 교정

v1 모델 목록500은 실제 LocalModelDiscovery의 독립 endpoint가 기본11434를 사용해 하네스 가드에 막힌 결과다. 제품 SSE/queued task는 미도달, login UI만 관찰했다. backend exit0, browser.close/profile 제거는 완료했으나 driver는 잔여 handle로 SIGINT 후 tool exit1이었다. 기존 자료를 보존한다.

v2는 AGK_OLLAMA_API_BASE를 소유503 fixture로 고정하고 LocalModelDiscovery 생성 인자만 소유 빈 models_dir·openai_endpoints=[]로 제한한다. 실제 discover/parser와 모델 route/registry merge/manager/provider/runtime/auth는 그대로 사용하며 inventory 결과나 UI/API 응답을 대체하지 않는다. home model cache와 다른 inference service를 접근하지 않는다. Synthetic tags/show와 실제 제어 HTTP503은 모델 품질/실제 설치 모델 검증이 아니다. live fixture model targets는 logical name과 wire alias 둘만 허용한다. browser.close·profile 제거 후 CLI를 명시 종료한다. 기존 frontend bundle fingerprint는 변경 없음을 확인해 사용한다.

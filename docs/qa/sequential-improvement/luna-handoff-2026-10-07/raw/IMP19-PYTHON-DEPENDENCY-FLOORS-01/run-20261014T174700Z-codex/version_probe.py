from __future__ import annotations

import importlib.metadata
import json

packages = ('anyio', 'pyjwt', 'fsspec', 'multidict', 'oauthlib', 'sentence-transformers', 'urllib3', 'chromadb', 'requests-oauthlib', 'typing-extensions')
print(json.dumps({name: importlib.metadata.version(name) for name in packages}, indent=2))

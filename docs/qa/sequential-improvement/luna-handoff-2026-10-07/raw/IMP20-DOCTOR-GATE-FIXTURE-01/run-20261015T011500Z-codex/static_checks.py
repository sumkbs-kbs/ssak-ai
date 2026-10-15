import json
from pathlib import Path
import subprocess
import sys

REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
BASE = Path(__file__).resolve().parent / sys.argv[1]
BASE.mkdir()
commands = {
    'type': [str(REPO / '.venv/bin/basedpyright'), '--outputjson', 'tests/test_doctor.py'],
    'lint': [str(REPO / '.venv/bin/ruff'), 'check', 'tests/test_doctor.py'],
    'format': [str(REPO / '.venv/bin/ruff'), 'format', '--check', 'tests/test_doctor.py'],
    'compile': [str(REPO / '.venv/bin/python'), '-B', '-c', 'from pathlib import Path; p=Path("tests/test_doctor.py"); compile(p.read_bytes(),str(p),"exec")'],
}
receipts = []
for name, command in commands.items():
    with (BASE / (name + '.stdout.txt')).open('xb') as stdout, (BASE / (name + '.stderr.txt')).open('xb') as stderr:
        result = subprocess.run(command, cwd=REPO, stdout=stdout, stderr=stderr, timeout=60)
    receipts.append({'name': name, 'command': command, 'exit_code': result.returncode})
(BASE / 'checks.json').write_text(json.dumps(receipts, indent=2) + '\n')
print(json.dumps(receipts))

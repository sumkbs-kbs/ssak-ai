from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


def _temporary_home(_cls: type[Path]) -> Path:
    return Path(os.environ["SSAK_JEV_QA_HOME"])


_home_patch = patch.object(Path, "home", classmethod(_temporary_home))
_ = _home_patch.start()

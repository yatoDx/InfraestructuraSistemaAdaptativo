import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def synth_dir(tmp_path_factory):
    """Conjunto sintético pequeño (1,5 h) generado una sola vez para todas las pruebas."""
    d = tmp_path_factory.mktemp("synth")
    subprocess.run([sys.executable, "-m", "generators.synth_flows", "--out", str(d), "--hours", "1.5"],
                   cwd=ROOT, check=True, capture_output=True)
    return d

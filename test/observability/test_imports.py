import json
from pathlib import Path
import subprocess
import sys


def test_fresh_process_dependency_isolation_and_source_origin():
    result = subprocess.run([sys.executable, "-I", "-c", """
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path.cwd() / 'src'))
import cacheroute.observability, cacheroute.observability.v1
for module in ('proxy','scheduler','instance','kdn_server','fastapi','redis','numpy','torch','vllm','lmcache'):
    assert module not in sys.modules, module
print(json.dumps([cacheroute.observability.__file__, cacheroute.observability.v1.__file__]))
"""], check=True, text=True, capture_output=True)
    paths = json.loads(result.stdout)
    assert all(Path(path).resolve().is_relative_to((Path.cwd() / "src").resolve()) for path in paths)
    assert not (Path.cwd() / "cacheroute_observability").exists()

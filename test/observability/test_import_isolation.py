import subprocess
import sys


def test_import_isolation_in_fresh_process():
    code = r'''
import sys
import cacheroute_observability
forbidden = {"fastapi", "httpx", "aiohttp", "redis", "numpy", "torch", "vllm",
             "lmcache", "core", "scheduler", "proxy", "instance", "kdn_server"}
loaded = {name.split(".", 1)[0] for name in sys.modules}
unexpected = forbidden & loaded
assert not unexpected, sorted(unexpected)
print("observability import isolation: passed")
'''
    result = subprocess.run([sys.executable, "-c", code], check=True, text=True,
                            capture_output=True)
    assert result.stdout.strip() == "observability import isolation: passed"

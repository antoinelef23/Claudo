"""Package shim: redirects the 'gateway' name to src/gateway during test collection.

When pytest finds tests/gateway/__init__.py it registers tests/gateway/ as the
'gateway' package, shadowing src/gateway. This shim replaces that registration
with the real src/gateway package while keeping tests/gateway/ in __path__ so
that pytest can still discover test files here.
"""

import importlib.util
import sys
from pathlib import Path

_tests_gateway = Path(__file__).parent
_src_gateway = Path(__file__).parents[2] / "src" / "gateway"
_src = str(_src_gateway.parent)

if _src not in sys.path:
    sys.path.insert(0, _src)

spec = importlib.util.spec_from_file_location(
    "gateway",
    str(_src_gateway / "__init__.py"),
    submodule_search_locations=[str(_src_gateway), str(_tests_gateway)],
)
_real_module = importlib.util.module_from_spec(spec)
sys.modules["gateway"] = _real_module
spec.loader.exec_module(_real_module)

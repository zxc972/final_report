"""Isolated host worker for the independent global reference, never a model mount."""

import importlib.util
import json
from pathlib import Path
import sys
import types


def main():
    root = Path(__file__).resolve().parent
    package = types.ModuleType("_global_host_reference")
    package.__path__ = [str(root)]
    sys.modules[package.__name__] = package
    for name in ("analysis_numeric_reference", "analysis_global_reference"):
        spec = importlib.util.spec_from_file_location(
            package.__name__ + "." + name, root / (name + ".py")
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    request = json.loads(sys.stdin.buffer.read(65536))
    reference = sys.modules[package.__name__ + ".analysis_global_reference"]
    result = reference.subject_globals(**request)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()

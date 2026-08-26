from pathlib import Path
import sys
from loto.parameter_effectiveness.contracts import ParameterSuiteSpec
from loto.parameter_effectiveness.core import AdapterRegistry, run_suite
from loto.parameter_effectiveness.toto2_adapter import Toto2MinimalParameterAdapter
spec = ParameterSuiteSpec.model_validate_json(Path(sys.argv[1]).read_text(encoding='utf-8'))
registry = AdapterRegistry()
registry.register(Toto2MinimalParameterAdapter(), 'toto')
results = run_suite(spec, registry, Path(sys.argv[2]))
print([item.model_dump(mode='json') for item in results])
raise SystemExit(0 if all(item.outcome.value == 'effective' for item in results) else 2)

import ast
from pathlib import Path
import unittest


class Q4Q6ContractTests(unittest.TestCase):
    def test_modules_are_isolated_equations(self):
        forbidden_imports = {'ledger', 'resolver'}
        forbidden_calls = {'calibration', 'aggregate', 'eligibility', 'weights'}
        for name in ('q4_stat_arb.py', 'q5_microstructure.py', 'q6_volume_liquidity.py'):
            source = (Path('quant') / name).read_text()
            tree = ast.parse(source)
            imports = {alias.name.lower() for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
            self.assertFalse(any(any(word in item for word in forbidden_imports) for item in imports))
            self.assertFalse(any(word in source.lower() for word in forbidden_calls))


if __name__ == '__main__': unittest.main()

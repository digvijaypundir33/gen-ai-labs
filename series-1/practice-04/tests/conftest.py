import importlib.util
import os
import sys

LAMBDA_DIR = os.path.join(os.path.dirname(__file__), "..", "lambda")


def import_lambda(function_name):
    """Import a Lambda's lambda_function.py by directory name, isolated from other Lambdas' modules."""
    path = os.path.join(LAMBDA_DIR, function_name, "lambda_function.py")
    spec = importlib.util.spec_from_file_location(f"{function_name}_lambda_function", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

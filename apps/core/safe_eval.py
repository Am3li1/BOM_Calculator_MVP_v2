"""
Safe arithmetic expression evaluator for user-defined resource formulas
(Resource.formula_expression).

Deliberately NOT using eval()/exec() — those execute arbitrary Python
(imports, attribute access, __class__ tricks, etc), which would be a
serious security hole given these expressions are typed by users
through a web form. Instead, the expression is parsed into an AST and
walked by hand, only permitting a small whitelist of node types,
operators, and function calls. Anything outside that whitelist raises
FormulaError immediately, before any evaluation happens.
"""
import ast
import operator


class FormulaError(Exception):
    """Raised for any invalid, unsafe, or unevaluable formula."""


_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Deliberately small — enough to handle real cases (e.g. "treat height
# as 1 if it's 0") without opening up arbitrary function calls.
_ALLOWED_FUNCS = {
    'max': max,
    'min': min,
    'abs': abs,
    'round': round,
}


def evaluate_formula(expression, variables):
    """
    Evaluates `expression` (a string) using only names present in
    `variables` (dict of str -> number) and the whitelisted operators/
    functions above.

    Raises FormulaError for: syntax errors, unknown variables,
    disallowed operators/functions, division by zero, or a result
    that isn't a plain number.
    """
    if not expression or not expression.strip():
        raise FormulaError('Formula is empty.')

    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
        raise FormulaError(f'Invalid syntax: {e.msg}')

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return node.value
            raise FormulaError(f'Only numbers are allowed, got: {node.value!r}')

        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise FormulaError(
                    f'Unknown variable "{node.id}". '
                    f'Available: {", ".join(sorted(variables))}'
                )
            return variables[node.id]

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_BINOPS:
                raise FormulaError(
                    f'Operator "{op_type.__name__}" is not allowed.'
                )
            left = _eval(node.left)
            right = _eval(node.right)
            try:
                return _ALLOWED_BINOPS[op_type](left, right)
            except ZeroDivisionError:
                raise FormulaError('Division by zero.')

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_UNARYOPS:
                raise FormulaError(
                    f'Unary operator "{op_type.__name__}" is not allowed.'
                )
            return _ALLOWED_UNARYOPS[op_type](_eval(node.operand))

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                allowed = ', '.join(sorted(_ALLOWED_FUNCS))
                raise FormulaError(
                    f'Function calls are only allowed for: {allowed}.'
                )
            if node.keywords:
                raise FormulaError('Keyword arguments are not supported.')
            args = [_eval(a) for a in node.args]
            return _ALLOWED_FUNCS[node.func.id](*args)

        raise FormulaError(
            f'"{type(node).__name__}" is not allowed in formulas.'
        )

    result = _eval(tree)

    if not isinstance(result, (int, float)) or isinstance(result, bool):
        raise FormulaError('Formula did not evaluate to a number.')

    return result
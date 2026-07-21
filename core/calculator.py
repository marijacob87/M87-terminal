import ast
import operator


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def is_calculation(text):
    text = text.strip()

    if not text:
        return False

    allowed = set("0123456789+-*/()., ")
    return all(char in allowed for char in text) and any(
        op in text for op in ["+", "-", "*", "/"]
    )


def safe_eval(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value

    if isinstance(node, ast.BinOp):
        operator_type = type(node.op)

        if operator_type in OPERATORS:
            return OPERATORS[operator_type](
                safe_eval(node.left),
                safe_eval(node.right),
            )

    if isinstance(node, ast.UnaryOp):
        operator_type = type(node.op)

        if operator_type in OPERATORS:
            return OPERATORS[operator_type](safe_eval(node.operand))

    raise ValueError("Cálculo inválido")


def _format_result(value):
    """Formata números sem a cauda infinita dos floats.

    Inteiros ficam sem casas decimais. Resultados quebrados usam no máximo
    cinco casas decimais e perdem zeros desnecessários no final.
    """
    if isinstance(value, float):
        if not (float("-inf") < value < float("inf")):
            raise ValueError("Resultado inválido")

        if value.is_integer():
            return str(int(value))

        text = f"{value:.5f}".rstrip("0").rstrip(".")
    else:
        text = str(value)

    return text.replace(".", ",")


def calculate(text):
    expression = text.strip().replace(",", ".")

    tree = ast.parse(expression, mode="eval")
    result = safe_eval(tree.body)

    return _format_result(result)

import ast

class StaticAnalyzer(ast.NodeVisitor):

    def __init__(self):
        self.functions = {}
        self.bugs = []

    def visit_FunctionDef(self, node):
        self.functions[node.name] = len(node.args.args)
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name in self.functions:
                expected = self.functions[name]  #def sum(a,b)
                actual = len(node.args)
                if expected != actual:
                    self.bugs.append(
                        {
                            "line": node.lineno,
                            "severity": "critical",
                            "description":
                                f"Function '{name}' expects "
                                f"{expected} arguments "
                                f"but received {actual}."
                        }
                    )
        self.generic_visit(node)


def analyze_static(code, language):
    if language != "Python":
        return []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    analyzer = StaticAnalyzer()
    analyzer.visit(tree)
    return analyzer.bugs
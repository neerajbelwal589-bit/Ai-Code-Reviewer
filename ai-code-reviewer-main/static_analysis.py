import ast


class StaticAnalyzer(ast.NodeVisitor):

    def __init__(self):
        # name -> (min_args, max_args or None if *args allowed)
        self.functions = {}
        self.duplicates = set()
        self.bugs = []

    def visit_FunctionDef(self, node):
        a = node.args
        total = len(a.posonlyargs) + len(a.args)
        min_args = total - len(a.defaults)
        max_args = None if a.vararg else total

        # same name defined twice (or inside a class) -> skip to avoid false alarms
        if node.name in self.functions:
            self.duplicates.add(node.name)
        self.functions[node.name] = (min_args, max_args)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        # methods have 'self', so don't register them as plain functions
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.duplicates.add(child.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name in self.functions and name not in self.duplicates:
                min_args, max_args = self.functions[name]

                # *args / **kwargs / keyword args in the call -> can't count safely
                has_star = any(isinstance(x, ast.Starred) for x in node.args)
                has_kw = bool(node.keywords)

                if not has_star and not has_kw:
                    actual = len(node.args)
                    too_few = actual < min_args
                    too_many = max_args is not None and actual > max_args
                    if too_few or too_many:
                        if max_args is None or min_args == max_args:
                            expected = str(min_args)
                        else:
                            expected = f"{min_args} to {max_args}"
                        self.bugs.append(
                            {
                                "line": node.lineno,
                                "severity": "critical",
                                "description": (
                                    f"Function '{name}' expects "
                                    f"{expected} arguments "
                                    f"but received {actual}."
                                ),
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

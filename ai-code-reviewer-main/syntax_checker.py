import ast

def check_syntax(code, language):
    if language!='Python':
        return{
            "valid":True,
            "bugs":[]
        }
    
    try:
        ast.parse(code)
        return{
            "valid":True,
            "bugs":[]
        }
    except SyntaxError as e:
        return {
            "valid":False,
            "bugs": {
                "line":e.lineno,
                "severity":"critical",
                "description":f"SyntaxError:{e.msg}"
            }
        }
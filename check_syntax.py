import ast
try:
    with open('main.py', 'r', encoding='utf-8') as f:
        source = f.read()
    ast.parse(source)
    print('No syntax error')
except SyntaxError as e:
    print(f'SyntaxError at line {e.lineno}: {e.text}')
    print(f'Error: {e.msg}')
except Exception as e:
    print(f'Other error: {e}')
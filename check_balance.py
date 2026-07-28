def check_balance(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        text = f.read()
    
    stack = []
    pairs = {')': '(', '}': '{', ']': '['}
    for i, char in enumerate(text):
        if char in '({[':
            stack.append((char, i))
        elif char in ')}]':
            if not stack:
                return f"Unmatched {char} at index {i}"
            top, _ = stack.pop()
            if top != pairs[char]:
                return f"Mismatched {char} at index {i}. Expected {pairs[char]} but got {top}"
    if stack:
        return f"Unclosed {stack[-1][0]} at index {stack[-1][1]}"
    return "Balanced!"

print("app.js:", check_balance('ui/app.js'))
print("helpers.js:", check_balance('ui/helpers.js'))

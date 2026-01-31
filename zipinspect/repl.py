from typing import List


class ReplSyntaxError(Exception):
    pass

def parse_args(line: str) -> List[str]:
    """Space delimited argument parser like the shell, but minimal."""
    parsed = []
    accum = ''
    escape = False
    quote = False

    for i, token in enumerate(line):
        if quote:
            if escape:
                if token in '\\"':
                    accum += token
                    escape = False
                else:
                    raise ReplSyntaxError(i, token)
            else:
                if token == '\\':
                    escape = True
                elif token == '"':
                    quote = False # Quote end
                else:
                    accum += token
        else:
            # Only append if accum is not empty
            if token == ' ' and accum != '':
                parsed.append(accum)
                accum = '' # Reset
            elif token == '"':
                quote = True # Quote start
            else:
                accum += token

    # Push the last argument
    if accum:
        parsed.append(accum)

    return parsed
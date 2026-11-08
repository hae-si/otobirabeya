"""Read PostgreSQL COPY text from a local gzip, without executing SQL."""
import gzip
import re


def decode_copy(value):
    if value == r'\N':
        return None
    result = bytearray()
    i = 0
    while i < len(value):
        if value[i] != '\\':
            result.extend(value[i].encode('utf-8'))
            i += 1
            continue
        i += 1
        if i == len(value):
            raise ValueError('Incomplete COPY escape')
        if value[i] in '01234567':
            match = re.match(r'[0-7]{1,3}', value[i:])
            result.append(int(match[0], 8))
            i += len(match[0])
        elif value[i] == 'x':
            match = re.match(r'[0-9a-fA-F]{1,2}', value[i + 1:])
            if not match:
                raise ValueError('Invalid COPY hexadecimal escape')
            result.append(int(match[0], 16))
            i += len(match[0]) + 1
        else:
            result.extend({'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r',
                           't': '\t', 'v': '\v'}.get(value[i], value[i]).encode('utf-8'))
            i += 1
    return result.decode('utf-8')


def read_copy(path, allowed):
    table = None
    seen_tables = set()
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        for line_number, line in enumerate(stream, 1):
            line = line.rstrip('\r\n')
            if table:
                if line == r'\.':
                    table = None
                    continue
                if table not in allowed:
                    continue
                values = line.split('\t')
                if len(values) != len(columns):
                    raise ValueError(f'COPY field count mismatch at line {line_number}: {table}')
                yield table, dict(zip(columns, map(decode_copy, values)))
            else:
                match = re.fullmatch(r'COPY public\.(\w+) \((.*?)\) FROM stdin;', line)
                if match:
                    table = match[1]
                    if table in seen_tables:
                        raise ValueError('Repeated COPY table: ' + table)
                    seen_tables.add(table)
                    columns = [c.strip('"') for c in match[2].split(', ')]
                    if len(columns) != len(set(columns)):
                        raise ValueError('Duplicate COPY column')
                elif line.startswith('COPY '):
                    raise ValueError('Unsupported COPY syntax')
    if table:
        raise ValueError('Unterminated COPY block: ' + table)
    if not set(allowed) <= seen_tables:
        raise ValueError('Missing COPY tables: ' + ', '.join(set(allowed) - seen_tables))

# -*- coding: utf-8 -*-
"""F3 收敛 pass 分析：找出三胞胎页面中规范化后逐字相同的顶层函数。用后即删。"""
import io
import re
import hashlib

BS = chr(92)  # backslash


def read_lf(p):
    return io.open(p, encoding='utf-8', newline='').read().replace('\r\n', '\n')


FUNC_RX = re.compile(r'^    (?:async )?function ([A-Za-z_$][\w$]*)\s*\(', re.M)


def functions(text):
    """Extract top-level (4-space indent) function declarations with bodies."""
    out = {}
    for m in FUNC_RX.finditer(text):
        name = m.group(1)
        start = m.start()
        i = text.index('{', m.end() - 1)
        depth = 0
        j = i
        in_str = None
        while j < len(text):
            c = text[j]
            if in_str:
                if c == BS:
                    j += 2
                    continue
                if c == in_str:
                    in_str = None
            elif c in ('"', "'", '`'):
                in_str = c
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out[name] = text[start:j + 1]
    return out


def norm(body):
    return re.sub(r'\s+', ' ', body).strip()


GROUPS = {
    'create': ['static/js/pages/google_sheet_c4_create.js',
               'static/js/pages/google_sheet_c5_create.js',
               'static/js/pages/google_sheet_c7_create.js'],
    'detail': ['static/js/pages/google_sheet_c4_detail.js',
               'static/js/pages/google_sheet_c5_detail.js',
               'static/js/pages/google_sheet_c7_detail.js'],
}

for g, files in GROUPS.items():
    print('=====', g)
    allf = [functions(read_lf(f)) for f in files]
    names = sorted(set.intersection(*[set(a) for a in allf]))
    identical, differing = [], []
    for n in names:
        sigs = {hashlib.md5(norm(a[n]).encode()).hexdigest() for a in allf}
        (identical if len(sigs) == 1 else differing).append(n)
    print('IDENTICAL across all three:')
    for n in identical:
        print('   %-38s %5d chars' % (n, len(allf[0][n])))
    print('common but DIFFERING (skip):')
    print('  ' + ', '.join(differing))

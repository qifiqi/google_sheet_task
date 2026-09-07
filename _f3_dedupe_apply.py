# -*- coding: utf-8 -*-
"""F3 批内收敛 pass（02 §3.6 两步走第二步）：把 c4/c5/c7 三胞胎中规范化后逐字相同的
顶层函数提升到 static/js/common/business/，页面 JS 调用点改写为 Biz.*。用后即删。

红线：只提取三版规范化后完全相同的函数；business 模块保持与页面一致的脚本模式
（不加 'use strict'，与原内联脚本一致）；静态 HTML 内联 onclick 调用点同步改写。
"""
import io
import re

ROOT = 'C:/Users/fuqing/Desktop/google_sheet_task'
BS = chr(92)

FORM_STATE = ['showError', 'syncSelectedTokenMeta', 'applyPendingTokenSelection',
              'renderGoogleSheetTokenOptions', 'loadGoogleSheetTokens', 'importGoogleSheetToken',
              'applyDateRangeModes', 'initDefaultDatesIfEmpty', 'initProductCodeChipsFromParam1',
              'renderProductCodeChips', 'initFromUrlParams', 'fillFormWithRestartTask',
              'loadStockMarkets']
TASK_SUBMIT = ['generateCombinations', 'clearAllParameters', 'saveAsTemplate', 'submitTemplate',
               'handleTaskEvent']
TASK_POLLING = ['getTaskIdFromUrl', 'getFrequencyText', 'manualRefresh', 'loadTaskLogs',
                'loadTaskResults', 'changeResultsPage', 'filterResults', 'applyResultsFilter',
                'renderResultsPagination', 'isPlainObject', 'getFlatResult',
                'getPreferredMetricValue', 'getFirstMetricValue', 'getModelSharpeValue',
                'getDetailMetricSource', 'shouldShowDetailMetric']
CONFIG_EDIT = ['openEditConfigModal', 'renderEditProductCodeChips', 'renderEditSheetsRows',
               'collectEditProductCodesFromChips', 'createConfigGridItem',
               'formatConfigDisplayValue', 'formatCountMode', 'formatDateRangeMode',
               'formatMarketType', 'formatTokenType']

# (业务模块文件, Biz 域名, 函数列表, 覆盖页面组)
MODULES = [
    ('form-state.js', 'formState', FORM_STATE, 'create'),
    ('task-submit.js', 'taskSubmit', TASK_SUBMIT, 'create'),
    ('task-polling.js', 'taskPolling', TASK_POLLING, 'detail'),
    ('config-edit.js', 'configEdit', CONFIG_EDIT, 'detail'),
]

PAGES = {
    'create': {
        'files': ['static/js/pages/google_sheet_c4_create.js',
                  'static/js/pages/google_sheet_c5_create.js',
                  'static/js/pages/google_sheet_c7_create.js'],
        'html': ['templates/google_sheet_c4/create.html',
                 'templates/google_sheet_c5/create.html',
                 'templates/google_sheet_c7/create.html'],
        'scripts': ['form-state.js', 'task-submit.js'],
    },
    'detail': {
        'files': ['static/js/pages/google_sheet_c4_detail.js',
                  'static/js/pages/google_sheet_c5_detail.js',
                  'static/js/pages/google_sheet_c7_detail.js'],
        'html': ['templates/google_sheet_c4/detail.html',
                 'templates/google_sheet_c5/detail.html',
                 'templates/google_sheet_c7/detail.html'],
        'scripts': ['task-polling.js', 'config-edit.js'],
    },
}

MODULE_HEADER = {
    'form-state.js': '// c4/c5/c7 创建页三胞胎共享：表单状态/Token 选择/产品 chips/URL 回填（02 §3.6，F3 收敛 pass）。',
    'task-submit.js': '// c4/c5/c7 创建页三胞胎共享：参数组合展开/保存模板/任务事件（02 §3.6，F3 收敛 pass）。',
    'task-polling.js': '// c4/c5/c7 详情页三胞胎共享：任务轮询/日志面板/结果分页（02 §3.6，F3 收敛 pass）。',
    'config-edit.js': '// c4/c5/c7 详情页三胞胎共享：编辑配置弹窗（02 §3.6，F3 收敛 pass）。',
}


def read_lf(p):
    return io.open(ROOT + '/' + p, encoding='utf-8', newline='').read().replace('\r\n', '\n')


def write_crlf(p, s):
    with io.open(ROOT + '/' + p, 'w', encoding='utf-8', newline='') as fh:
        fh.write(s.replace('\n', '\r\n'))
    print('written', p, len(s), 'chars')


def find_functions(text):
    """返回 {name: (indent, start, end)}，顶层 function 声明（任意缩进）。"""
    rx = re.compile(r'^([ ]*)(?:async )?function ([A-Za-z_$][\w$]*)\s*\([^)]*\) \{', re.M)
    out = {}
    for m in rx.finditer(text):
        name = m.group(2)
        indent, start = m.group(1), m.start()
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
        out[name] = (indent, start, j + 1)
    return out


def norm(s):
    return re.sub(r'\s+', ' ', s).strip()


def delete_block(text, loc):
    _, start, end = loc
    # 同时吞掉函数块后紧跟的空行（保持页面行数整洁）
    m = re.match(r'\n[ ]*\n', text[end:end + 16])
    consume = end + (m.end() if m else 0)
    return text[:start] + text[consume:]


def main():
    moved = {}   # name -> (module_file, domain, canonical_body)
    for module_file, domain, names, group in MODULES:
        for n in names:
            moved[n] = [module_file, domain, group, None]

    # 1) 以 c4 版本为正本提取函数体，并校验三版原始文本仅空白差异
    for group in ('create', 'detail'):
        texts = {f: read_lf(f) for f in PAGES[group]['files']}
        locs = {f: find_functions(t) for f, t in texts.items()}
        for name, spec in moved.items():
            if spec[2] != group:
                continue
            bodies = []
            for f in PAGES[group]['files']:
                assert name in locs[f], '%s missing %s' % (f, name)
                _, s, e = locs[f][name]
                bodies.append(texts[f][s:e])
            canon = bodies[0]
            for f, b in zip(PAGES[group]['files'], bodies):
                assert norm(b) == norm(canon), 'non-whitespace diff for %s in %s' % (name, f)
            spec[3] = canon

    # 2) 生成 business 模块
    for module_file, domain, names, group in MODULES:
        parts = [
            '// ' + '-' * 30,
            MODULE_HEADER[module_file],
            '// 来源：static/js/pages/google_sheet_c{4,5,7}_%s.js（三版规范化后逐字相同，正本取自 c4）。' % group,
            '// 页面差异逻辑仍留在 pages 层；页面调用点经 Biz.%s.* 访问。' % domain,
            '// ' + '-' * 30,
            '(function () {',
            '    window.Biz = window.Biz || {};',
            '',
        ]
        for n in names:
            body = moved[n][3]
            # 去掉原 4 空格页面缩进，改为模块内 4 空格
            lines = body.split('\n')
            dedented = []
            for ln in lines:
                dedented.append(ln[4:] if ln.startswith('    ') else ln)
            parts.append('    ' + '\n    '.join(dedented))
            parts.append('')
        parts.append('    Biz.%s = {' % domain)
        parts.append(',\n'.join('        %s: %s' % (n, n) for n in names))
        parts.append('    };')
        parts.append('})();')
        write_crlf('static/js/common/business/' + module_file, '\n'.join(parts) + '\n')

    # 3) 页面 JS：删除本地副本 + 调用点改写 Biz.*
    for group in ('create', 'detail'):
        name_domain = {n: d for _, d, names, g in MODULES for n in names if g == group}
        for f in PAGES[group]['files']:
            t = read_lf(f)
            locs = find_functions(t)
            # 删除本地副本（每删一个重新定位，避免偏移失效）
            for name in name_domain:
                locs = find_functions(t)
                assert name in locs, '%s: %s not found' % (f, name)
                t = delete_block(t, locs[name])
            # 调用点改写
            for name, domain in name_domain.items():
                rx = re.compile(r'\b%s\(' % re.escape(name))
                n = len(rx.findall(t))
                t = rx.sub('Biz.%s.%s(' % (domain, name), t)
                print('%s: %s -> Biz.%s.%s  (%d call sites)' % (f, name, domain, name, n))
            # 页面头注释补记收敛信息
            t = t.replace('// 自 templates/', '// 批内收敛：同名函数已提升至 static/js/common/business/（Biz.*），见 F3 收敛 pass。\n// 自 templates/', 1)
            write_crlf(f, t)

    # 4) 静态 HTML：onclick 调用点改写 + business 脚本引入
    html_rw = {
        'create': [
            ('onclick="saveAsTemplate()"', 'onclick="Biz.taskSubmit.saveAsTemplate()"'),
            ('onclick="submitTemplate()"', 'onclick="Biz.taskSubmit.submitTemplate()"'),
        ],
        'detail': [
            ("onclick=\"filterResults('all')\"", "onclick=\"Biz.taskPolling.filterResults('all')\""),
            ("onclick=\"filterResults('success')\"", "onclick=\"Biz.taskPolling.filterResults('success')\""),
            ("onclick=\"filterResults('failed')\"", "onclick=\"Biz.taskPolling.filterResults('failed')\""),
            ('onclick="openEditConfigModal()"', 'onclick="Biz.configEdit.openEditConfigModal()"'),
        ],
    }
    for group in ('create', 'detail'):
        for f in PAGES[group]['html']:
            t = read_lf(f)
            for old, new in html_rw[group]:
                n = t.count(old)
                assert n >= 1, '%s: %s not found' % (f, old)
                t = t.replace(old, new)
            inject = '\n'.join('    <script src="/static/js/common/business/%s"></script>' % s
                               for s in PAGES[group]['scripts'])
            marker = '<script src="/static/js/pages/'
            i = t.index(marker)
            t = t[:i] + inject + '\n' + t[i:]
            write_crlf(f, t)
    print('done')


if __name__ == '__main__':
    main()

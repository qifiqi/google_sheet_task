# -*- coding: utf-8 -*-
"""F3 批次静态化转换器（c4/c5/c7 create+detail）。用后即删。

机械搬移 + 受控改写：
- Jinja 骨架展开为静态 HTML（02 §2 骨架）；
- `{% if template_id %}` 死代码删除（路由从未注入）；
- `{{ version }}` → `${CURRENT_VERSION}`（03 §5）；
- `url_for(...)` → 字面量 + 页面 JS 运行时改写返回链接；
- fetch/ajaxRequest → Api.endpoints.*（wire 零变化，err.message 即原信封 message）。
"""
import io
import re
import sys

ROOT = 'C:/Users/fuqing/Desktop/google_sheet_task'

PAGES = {
    'c4create': dict(
        src='templates/google_sheet_c4/create.html', kind='create', ver='c4',
        title='创建任务 - Google Sheet C4 参数批量校验', page_js='google_sheet_c4_create'),
    'c4detail': dict(
        src='templates/google_sheet_c4/detail.html', kind='detail', ver='c4',
        title='任务详情 - Google Sheet C4 参数批量校验', page_js='google_sheet_c4_detail'),
    'c5create': dict(
        src='templates/google_sheet_c5/create.html', kind='create', ver='c5',
        title='创建任务 - Google Sheet C5 参数批量校验', page_js='google_sheet_c5_create'),
    'c5detail': dict(
        src='templates/google_sheet_c5/detail.html', kind='detail', ver='c5',
        title='任务详情 - Google Sheet C5 参数批量校验', page_js='google_sheet_c5_detail'),
    'c7create': dict(
        src='templates/google_sheet_c7/create.html', kind='create', ver='c7',
        title='创建任务 - Google Sheet C5 参数批量校验', page_js='google_sheet_c7_create'),
    'c7detail': dict(
        src='templates/google_sheet_c7/detail.html', kind='detail', ver='c7',
        title='任务详情 - Google Sheet c7 参数批量校验', page_js='google_sheet_c7_detail'),
}

SKELETON = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
{links}
    <script src="/static/js/bootstrap.bundle.min.js"></script>
</head>
<body class="template-auth-pending">
    <div class="template-auth-loading" id="templateAuthLoading">
        <div class="template-auth-loading__card">
            <div class="spinner-border text-primary" role="status" aria-hidden="true"></div>
            <div class="template-auth-loading__label" id="templateAuthLoadingLabel">正在恢复登录状态...</div>
        </div>
    </div>

    <div data-navbar></div>

    <div class="container mt-4" data-template-main-content>
{content}
    </div>

    <script src="/static/js/template-auth.js?v=20260415_page_scope"></script>
    <script src="/static/js/trading-date.js"></script>
    <script src="/static/js/common/components/navbar.js"></script>
    <script src="/static/js/common/api.js"></script>
    <script src="/static/js/common/utils.js"></script>
    <script src="/static/js/pages/{page_js}.js"></script>
</body>
</html>
"""


def read_lf(path):
    with io.open(ROOT + '/' + path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read().replace('\r\n', '\n')


def write_crlf(path, text):
    full = ROOT + '/' + path
    with io.open(full, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text.replace('\n', '\r\n'))
    print('written', path, len(text), 'chars')


class Ctx(object):
    def __init__(self, name, text):
        self.name = name
        self.text = text

    def rep(self, old, new, cnt=1):
        n = self.text.count(old)
        if n != cnt:
            raise SystemExit('[%s] rep: expected %d found %d:\n---\n%s\n---' % (self.name, cnt, n, old))
        self.text = self.text.replace(old, new)

    def rex(self, pattern, new, cnt=1):
        rx = re.compile(pattern)
        n = len(rx.findall(self.text))
        if n != cnt:
            raise SystemExit('[%s] rex: expected %d found %d: %s' % (self.name, cnt, n, pattern))
        self.text = rx.sub(new, self.text)

    def finish(self, forbid_jinja=True):
        for bad in ('fetch(', 'ajaxRequest('):
            if bad in self.text:
                raise SystemExit('[%s] leftover %s' % (self.name, bad))
        if forbid_jinja:
            for bad in ('{%', '{{'):
                if bad in self.text:
                    raise SystemExit('[%s] leftover jinja %s' % (self.name, bad))


def dedent4(block):
    return '\n'.join(line[4:] if line.startswith('    ') else line for line in block.split('\n'))


def scoped(t, start_marker, end_marker, pairs):
    """在 [start_marker 行首, end_marker 行首) 区间内做替换。"""
    s = t.text.index(start_marker)
    e = t.text.index(end_marker, s)
    seg = t.text[s:e]
    for old, new, cnt in pairs:
        n = seg.count(old)
        if cnt is None:
            if n == 0:
                raise SystemExit('[%s] scoped: no %r' % (t.name, old))
        elif n != cnt:
            raise SystemExit('[%s] scoped: expected %s found %d for %r' % (t.name, cnt, n, old))
        seg = seg.replace(old, new)
    t.text = t.text[:s] + seg + t.text[e:]


def extract_blocks(cfg):
    """返回 (content, css_inner or None, js)。按标记定位，全部 LF。"""
    raw = read_lf(cfg['src'])
    lines = raw.split('\n')

    def find(pred, start=0):
        for i in range(start, len(lines)):
            if pred(lines[i].strip()):
                return i
        return None

    b_content = find(lambda l: l == '{% block content %}')
    e_content = find(lambda l: l == '{% endblock %}', b_content + 1)
    content = '\n'.join(lines[b_content + 1:e_content])

    b_scripts = find(lambda l: l == '{% block scripts %}', e_content + 1)
    b_style = find(lambda l: l == '<style>', b_scripts + 1)
    if b_style is not None:
        e_style = find(lambda l: l == '</style>', b_style + 1)
        css_inner = '\n'.join(lines[b_style + 1:e_style])
        b_script = find(lambda l: l == '<script>', e_style + 1)
    else:
        css_inner = None
        b_script = find(lambda l: l == '<script>', b_scripts + 1)
    e_script = find(lambda l: l == '</script>', b_script + 1)
    js = '\n'.join(lines[b_script + 1:e_script])
    return content, css_inner, js


def back_link_block(ver):
    return (
        "\n"
        "// ── 原 Jinja 服务端渲染点的前端等价实现（静态化，docs/design/frontend-refactor/03 §5）──\n"
        "// 原 `url_for('google_sheet.index', version=request.args.get('version', '" + ver + "'))`\n"
        "const versionParam = new URLSearchParams(location.search).get('version');\n"
        "if (versionParam && versionParam !== '" + ver + "') {\n"
        "    const backLink = document.querySelector('a[href=\"/google-sheet/?version=" + ver + "\"]');\n"
        "    if (backLink) {\n"
        "        backLink.href = '/google-sheet/?version=' + encodeURIComponent(versionParam);\n"
        "    }\n"
        "}\n")


def url_for_replace(ver):
    old = "href=\"{{ url_for('google_sheet.index', version=request.args.get('version', '" + ver + "')) }}\""
    new = 'href="/google-sheet/?version=' + ver + '"'
    return old, new


# ─────────────────────────── create 页 ───────────────────────────

def conv_create(cfg, js):
    ver = cfg['ver']
    C = Ctx(cfg['page_js'], js)

    # Jinja 死代码：{% if template_id %} 块（路由从未注入 template_id，按渲染结果移除）
    dead = (
        "                {% if template_id %}\n"
        "                document.title = '从模板创建任务 - Google Sheet 参数批量校验';\n"
        "                const cardHeader = document.querySelector('.card-header h4');\n"
        "                if (cardHeader) {\n"
        "                    cardHeader.innerHTML = '<i class=\"bi bi-file-earmark-text\"></i> 从模板创建任务';\n"
        "                }\n"
        "                {% endif %}\n")
    if '{% if template_id %}' in C.text:
        C.rep(dead, '')

    # /api/meta/enums
    C.rep(
        "        const response = await fetch('/api/meta/enums');\n"
        "        const payload = await response.json();\n"
        "        select.innerHTML = (payload?.data?.stock_markets || []).map((market) =>\n",
        "        const payload = await Api.endpoints.meta.enums();\n"
        "        select.innerHTML = (payload?.stock_markets || []).map((market) =>\n")

    # /api/google-sheets 列表（c5/c7）
    if ver in ('c5', 'c7'):
        C.rep(
            "        return fetch(`/api/google-sheets?only_available=1&table_type=${encodeURIComponent(GOOGLE_SHEET_TABLE_TYPE)}`)\n"
            "            .then(response => response.json())\n"
            "            .then(data => {\n"
            "                if (data.status !== 'success') {\n"
            "                    throw new Error(data.message || '加载 Google Sheet 列表失败');\n"
            "                }\n"
            "\n"
            "                const items = Array.isArray(data.data?.items) ? data.data.items : [];\n",
            "        return Api.endpoints.googleSheet.sheets(`only_available=1&table_type=${encodeURIComponent(GOOGLE_SHEET_TABLE_TYPE)}`)\n"
            "            .then(data => {\n"
            "                const items = Array.isArray(data?.items) ? data.items : [];\n")

    # /api/google-sheet/worksheets
    if ver == 'c4':
        C.rep(
            "        // 发送请求获取工作表列表\n"
            "        fetch('/api/google-sheet/worksheets', {\n"
            "            method: 'POST',\n"
            "            headers: {\n"
            "                'Content-Type': 'application/json',\n"
            "            },\n"
            "            body: JSON.stringify(requestData)\n"
            "        })\n"
            "        .then(response => response.json())\n"
            "        .then(data => {\n"
            "            if (data.status === 'success' && Array.isArray(data.data.worksheets)) {\n"
            "                if (data.data.worksheets.length === 0) {\n",
            "        // 发送请求获取工作表列表\n"
            "        Api.endpoints.googleSheet.worksheets(requestData)\n"
            "        .then(data => {\n"
            "            if (Array.isArray(data.worksheets)) {\n"
            "                if (data.worksheets.length === 0) {\n")
        scoped(C, "// 获取单个配置块的工作表列表", "// 保持原有接口，默认针对第一组主配置块", [
            ("data.data?.title", "data.title", 1),
            ("data.data.title.trim()", "data.title.trim()", 2),
            ("data.data.worksheets", "data.worksheets", None),
        ])
    elif ver == 'c7':
        C.rep(
            "        return fetch('/api/google-sheet/worksheets', {\n"
            "            method: 'POST',\n"
            "            headers: {\n"
            "                'Content-Type': 'application/json',\n"
            "            },\n"
            "            body: JSON.stringify(requestData)\n"
            "        })\n"
            "            .then(response => response.json())\n"
            "            .then(data => {\n"
            "                if (!(data.status === 'success' && Array.isArray(data.data.worksheets))) {\n"
            "                    throw new Error(data.message || '获取工作表列表失败');\n"
            "                }\n"
            "\n"
            "                const sheetTitle = typeof data.data.title === 'string' ? data.data.title.trim() : '';\n"
            "                if (titleInput && sheetTitle) {\n"
            "                    titleInput.value = sheetTitle;\n"
            "                }\n"
            "                const isManualModelVersion = modelVersionSelect?.dataset.manual === 'true';\n"
            "                if (modelVersionSelect && !isManualModelVersion) {\n"
            "                    modelVersionSelect.value = sheetTitle.startsWith('C7.0.3') ? 'c7_0_3' : 'c7_0_2';\n"
            "                }\n"
            "                worksheetInput.value = Array.isArray(data.data.worksheets) && data.data.worksheets.length > 0\n"
            "                    ? (data.data.worksheets[0] || '')\n"
            "                    : '';\n",
            "        return Api.endpoints.googleSheet.worksheets(requestData)\n"
            "            .then(data => {\n"
            "                if (!Array.isArray(data.worksheets)) {\n"
            "                    throw new Error(data.message || '获取工作表列表失败');\n"
            "                }\n"
            "\n"
            "                const sheetTitle = typeof data.title === 'string' ? data.title.trim() : '';\n"
            "                if (titleInput && sheetTitle) {\n"
            "                    titleInput.value = sheetTitle;\n"
            "                }\n"
            "                const isManualModelVersion = modelVersionSelect?.dataset.manual === 'true';\n"
            "                if (modelVersionSelect && !isManualModelVersion) {\n"
            "                    modelVersionSelect.value = sheetTitle.startsWith('C7.0.3') ? 'c7_0_3' : 'c7_0_2';\n"
            "                }\n"
            "                worksheetInput.value = Array.isArray(data.worksheets) && data.worksheets.length > 0\n"
            "                    ? (data.worksheets[0] || '')\n"
            "                    : '';\n")
    else:
        C.rep(
            "        return fetch('/api/google-sheet/worksheets', {\n"
            "            method: 'POST',\n"
            "            headers: {\n"
            "                'Content-Type': 'application/json',\n"
            "            },\n"
            "            body: JSON.stringify(requestData)\n"
            "        })\n"
            "            .then(response => response.json())\n"
            "            .then(data => {\n"
            "                if (!(data.status === 'success' && Array.isArray(data.data.worksheets))) {\n"
            "                    throw new Error(data.message || '获取工作表列表失败');\n"
            "                }\n"
            "\n"
            "                if (titleInput && typeof data.data.title === 'string' && data.data.title.trim() !== '') {\n"
            "                    titleInput.value = data.data.title.trim();\n"
            "                }\n"
            "                worksheetInput.value = Array.isArray(data.data.worksheets) && data.data.worksheets.length > 0\n"
            "                    ? (data.data.worksheets[0] || '')\n"
            "                    : '';\n",
            "        return Api.endpoints.googleSheet.worksheets(requestData)\n"
            "            .then(data => {\n"
            "                if (!Array.isArray(data.worksheets)) {\n"
            "                    throw new Error(data.message || '获取工作表列表失败');\n"
            "                }\n"
            "\n"
            "                if (titleInput && typeof data.title === 'string' && data.title.trim() !== '') {\n"
            "                    titleInput.value = data.title.trim();\n"
            "                }\n"
            "                worksheetInput.value = Array.isArray(data.worksheets) && data.worksheets.length > 0\n"
            "                    ? (data.worksheets[0] || '')\n"
            "                    : '';\n")

    # /api/google-sheet-tokens
    C.rep(
        "        fetch('/api/google-sheet-tokens')\n"
        "            .then(response => response.json())\n"
        "            .then(data => {\n"
        "                if (data.status !== 'success') {\n"
        "                    throw new Error(data.message || '加载Token失败');\n"
        "                }\n"
        "                googleSheetTokens = Array.isArray(data.data.tokens) ? data.data.tokens : [];\n"
        "                googleSheetRandomValue = data.data.random_value || '__random__';\n"
        "                renderGoogleSheetTokenOptions(googleSheetTokens);\n"
        "            })\n",
        "        Api.endpoints.googleSheet.tokens()\n"
        "            .then(data => {\n"
        "                googleSheetTokens = Array.isArray(data.tokens) ? data.tokens : [];\n"
        "                googleSheetRandomValue = data.random_value || '__random__';\n"
        "                renderGoogleSheetTokenOptions(googleSheetTokens);\n"
        "            })\n")

    # /api/google-sheet-tokens/import（c4 读信封顶层 data.token，c5/c7 读 data.data.token，解包后统一为 data.token）
    C.rex(
        r"fetch\('/api/google-sheet-tokens/import', \{\n"
        r"            method: 'POST',\n"
        r"            headers: \{\n"
        r"                'Content-Type': 'application/json',\n"
        r"            \},\n"
        r"            body: JSON\.stringify\(\{ token_file: tokenFile \}\)\n"
        r"        \}\)\n"
        r"            \.then\((?:resp|response) => (?:resp|response)\.json\(\)\)\n"
        r"            \.then\(data => \{\n"
        r"                if \(data\.status !== 'success'\) \{\n"
        r"                    throw new Error\(data\.message \|\| '导入Token失败'\);\n"
        r"                \}\n"
        r"                showNotification\(data\.message \|\| 'Token导入成功', 'success'\);\n"
        r"                pendingTokenSelection = \{ token_id: (?:data\.data\.|data\.)?token && (?:data\.data\.|data\.)?token\.id \? String\((?:data\.data\.|data\.)?token\.id\) : '' \};\n"
        r"                loadGoogleSheetTokens\(\);\n",
        "Api.endpoints.googleSheet.importToken({ token_file: tokenFile })\n"
        "            .then(data => {\n"
        "                showNotification(data.message || 'Token导入成功', 'success');\n"
        "                pendingTokenSelection = { token_id: data.token && data.token.id ? String(data.token.id) : '' };\n"
        "                loadGoogleSheetTokens();\n")

    # /api/tasks/<id>（restart 回填）
    C.rex(
        r"fetch\(`/api/tasks/\$\{encodeURIComponent\(taskId\)\}`\)\n"
        r"            \.then\((?:resp|response) => (?:resp|response)\.json\(\)\)\n"
        r"            \.then\(data => \{\n"
        r"                const task = \(data && data\.data && data\.data\.task\) \? data\.data\.task : null;\n",
        "Api.endpoints.task.detail(encodeURIComponent(taskId))\n"
        "            .then(data => {\n"
        "                const task = (data && data.task) ? data.task : null;\n")

    # /api/templates?task_type=...（模板列表）
    m = re.search(r"fetch\('/api/templates\?task_type=(google_sheet_C4|google_sheet_C5|google_sheet_c7)'\)\n"
                  r"            \.then\(response => response\.json\(\)\)\n"
                  r"            \.then\(data => \{\n"
                  r"                if \(!data \|\| !data\.status === 'success' \|\| !\(data\.data && Array\.isArray\(data\.data\.templates\)\)\) \{\n"
                  r"                    console\.error\('Invalid response format:', data\);\n"
                  r"                    return;\n"
                  r"                \}\n",
                  C.text)
    if not m:
        raise SystemExit('[%s] loadTemplates pattern not found' % C.name)
    C.text = C.text[:m.start()] + (
        "Api.endpoints.template.list('" + m.group(1) + "')\n"
        "            .then(data => {\n"
        "                if (!data || !Array.isArray(data.templates)) {\n"
        "                    console.error('Invalid response format:', data);\n"
        "                    return;\n"
        "                }\n") + C.text[m.end():]
    C.rep("data.data.templates.forEach(template => {", "data.templates.forEach(template => {")

    # /api/templates/<id>（模板回填）
    C.rep(
        "        fetch(`/api/templates/${templateId}`)\n"
        "            .then(response => response.json())\n"
        "            .then(template => {\n"
        "                let config = template.data.config;\n",
        "        Api.endpoints.template.detail(templateId)\n"
        "            .then(template => {\n"
        "                let config = template.config;\n")

    # POST /api/tasks（提交任务，原 ajaxRequest 回调 → promise，F2 同法）
    m = re.search(r"ajaxRequest\('/api/tasks', 'POST', taskData, function(?P<sp> ?)\(err, data\) \{\n(?P<body>.*?)\n        \}\);",
                  C.text, re.S)
    if not m:
        raise SystemExit('[%s] submitTask pattern not found' % C.name)
    sp = m.group('sp')
    mi = re.search(r"^ {12}if \(!err && data && data\.status === 'success'\) \{\n(?P<success>.*?)\n"
                   r" {12}\} else \{\n"
                   r" {16}showNotification\('创建任务失败: ' \+ \(data \? data\.message : '未知错误'\), 'error'\);\n"
                   r" {12}\}$", m.group('body'), re.S | re.M)
    if not mi:
        raise SystemExit('[%s] submitTask body pattern not found' % C.name)
    success = dedent4(mi.group('success')).replace('data.data.', 'data.')
    new = ("Api.endpoints.task.create(taskData).then(function" + sp + "(data) {\n"
           "            executeBtn.disabled = false;\n"
           "            executeBtn.innerHTML = '<i class=\"bi bi-play-circle\"></i> 创建任务并执行';\n"
           "\n"
           + success + "\n"
           "        }).catch(function" + sp + "(err) {\n"
           "            executeBtn.disabled = false;\n"
           "            executeBtn.innerHTML = '<i class=\"bi bi-play-circle\"></i> 创建任务并执行';\n"
           "\n"
           "            showNotification('创建任务失败: ' + (err && err.message ? err.message : '未知错误'), 'error');\n"
           "        });")
    C.text = C.text[:m.start()] + new + C.text[m.end():]

    # POST /api/templates（保存为模板）
    pat = (r"fetch\('/api/templates', \{\n"
           r"            method: 'POST',\n"
           r"            headers: \{\n"
           r"                'Content-Type': 'application/json',\n"
           r"            \},\n"
           r"            body: JSON\.stringify\(templateData\)\n"
           r"        \}\)\n"
           r"        \.then\(response => response\.json\(\)\)\n"
           r"        \.then\(data => \{\n"
           r"            if \(data\.status === 'success'\) \{\n"
           r"(?P<success>.*?)\n"
           r"            \} else \{\n"
           r"                showError\(data\.message \|\| '保存模板失败'\);\n"
           r"            \}\n"
           r"        \}\)\n"
           r"        \.catch\(error => \{\n"
           r"            console\.error\('保存模板失败:', error\);\n"
           r"            showError\('保存模板失败: ' \+ error\.message\);\n"
           r"        \}\);")
    m = re.search(pat, C.text, re.S)
    if not m:
        raise SystemExit('[%s] submitTemplate pattern not found' % C.name)
    success = dedent4(m.group('success')).replace('data.data.', 'data.')
    new = ("Api.endpoints.template.create(templateData)\n"
           "        .then(data => {\n"
           + success + "\n"
           "        })\n"
           "        .catch(error => {\n"
           "            console.error('保存模板失败:', error);\n"
           "            showError((error && error.message) || '保存模板失败');\n"
           "        });")
    C.text = C.text[:m.start()] + new + C.text[m.end():]

    C.finish()
    return C.text


# ─────────────────────────── detail 页 ───────────────────────────

ERR_SIMPLE = ("(err && err.message ? err.message : '未知错误')")
ERR_NESTED_OLD = "(data && data.message) ? data.message : (err ? err.message : '未知错误')"
ERR_NESTED_NEW = "(err && err.message) ? err.message : '未知错误'"


def transform_err(err):
    err = err.replace(ERR_NESTED_OLD, ERR_NESTED_NEW)
    err = err.replace("(data ? data.message : '未知错误')", ERR_SIMPLE)
    err = err.replace("// 处理错误情况 - data可能包含错误信息，即使err存在",
                      "// 处理错误情况 - err.message 即原信封 message")
    return err


def dedent_n(block, n):
    out = []
    for line in block.split('\n'):
        out.append(line[n:] if line[:n].strip() == '' else line)
    return '\n'.join(out)


def split_if_else_rebuild(C, site_pat, api_expr, keep_condition=False, success_extra=()):
    """把 `ajaxRequest(URL, METHOD, ARGS, function(err, data) { if (cond) {S} else {E} });`
    改写为 `Api...then(function(data) {S}).catch(function(err) {E'})`（F2 同法）。"""
    rx = re.compile(r"(?P<hind>[ ]*)ajaxRequest\(" + site_pat + r", function(?P<sp> ?)\(err, data\) \{\n"
                    r"(?P<body>.*?)\n"
                    r"(?P=hind)\}\);", re.S)
    m = rx.search(C.text)
    if not m:
        raise SystemExit('[%s] split_if_else: no match for %s' % (C.name, site_pat))
    hind, sp, body = m.group('hind'), m.group('sp'), m.group('body')
    mi = re.search(r"^(?P<i4>[ ]*)if \((?P<cond>[^\n]*)\) \{\n(?P<success>.*?)\n(?P=i4)\} else \{\n(?P<err>.*?)\n(?P=i4)\}$",
                   body, re.S | re.M)
    if not mi:
        raise SystemExit('[%s] split_if_else: body shape mismatch for %s' % (C.name, site_pat))
    cut = len(mi.group('i4')) - len(hind)
    if cut <= 0:
        raise SystemExit('[%s] split_if_else: unexpected indent for %s' % (C.name, site_pat))
    success = mi.group('success')
    for old, new in success_extra:
        n = success.count(old)
        if n == 0:
            raise SystemExit('[%s] success_extra not found: %r' % (C.name, old))
        success = success.replace(old, new)
    err = transform_err(mi.group('err'))
    new = (hind + api_expr + ".then(function" + sp + "(data) {\n"
           + dedent_n(success, cut) + "\n"
           + hind + "}).catch(function" + sp + "(err) {\n"
           + dedent_n(err, cut) + "\n"
           + hind + "});")
    C.text = C.text[:m.start()] + new + C.text[m.end():]


def conv_detail(cfg, js):
    ver = cfg['ver']
    C = Ctx(cfg['page_js'], js)

    # JS 模板字符串内的 {{ version }}（03 §5）
    if ver in ('c5', 'c7'):
        C.rep("version={{ version }}", "version=${CURRENT_VERSION}", cnt=2)

    # /api/config（默认刷新频率；失败分支原样落到 loadTaskDetail + startAutoRefresh）
    C.rex(r"ajaxRequest\('/api/config', 'GET', null, function ?\(err, data\) \{\n"
          r"                if \(!err && data && data\.data\.config && data\.data\.config\.detail_refresh_interval\) \{\n"
          r"                    currentRefreshFrequency = data\.data\.config\.detail_refresh_interval;",
          "Api.endpoints.config.get().then(function(data) {\n"
          "                if (data && data.config && data.config.detail_refresh_interval) {\n"
          "                    currentRefreshFrequency = data.config.detail_refresh_interval;")
    C.rep(
        "                loadTaskDetail();\n"
        "                // 启动自动刷新\n"
        "                startAutoRefresh();\n"
        "            });\n",
        "                loadTaskDetail();\n"
        "                // 启动自动刷新\n"
        "                startAutoRefresh();\n"
        "            }).catch(function() {\n"
        "                // 原 ajaxRequest 失败分支：仍按默认频率加载并启动自动刷新\n"
        "                loadTaskDetail();\n"
        "                startAutoRefresh();\n"
        "            });\n")

    # GET /api/tasks/<id>（任务详情轮询）
    C.rex(r"ajaxRequest\(`/api/tasks/\$\{currentTaskId\}`, 'GET', null, function ?\(err, data\) \{\n"
          r"            console\.log\('API响应:', err, data\);\n"
          r"            if \(!err && data && data\.data && data\.data\.task\) \{\n"
          r"                const task = data\.data\.task;",
          "Api.endpoints.task.detail(currentTaskId).then(function(data) {\n"
          "            console.log('API响应:', data);\n"
          "            if (data && data.task) {\n"
          "                const task = data.task;")
    C.rep(
        "            } else {\n"
        "                showNotification('获取任务详情失败: ' + (data ? data.message : '未知错误'), 'error');\n"
        "            }\n"
        "        });\n",
        "            } else {\n"
        "                showNotification('获取任务详情失败: ' + (data ? data.message : '未知错误'), 'error');\n"
        "            }\n"
        "        }).catch(function(err) {\n"
        "            showNotification('获取任务详情失败: ' + (err && err.message ? err.message : '未知错误'), 'error');\n"
        "        });\n")

    # GET /api/tasks/<id>/logs（日志面板）
    C.rex(r"ajaxRequest\(`/api/tasks/\$\{currentTaskId\}/logs\`, 'GET', null, function ?\(err, data\) \{",
          "Api.endpoints.task.logs(currentTaskId).then(function(data) {")
    C.rep("console.log('日志API响应:', err, data);", "console.log('日志API响应:', data);")
    C.rep("if (!err && data && data.data && data.data.logs) {", "if (data && data.logs) {")
    scoped(C, "// 加载任务日志", "// 加载任务参数", [("data.data.logs", "data.logs", None)])
    C.rep(
        "            } else {\n"
        "                console.error('加载日志失败:', err, data);\n"
        "                const logContainer = document.getElementById('log-container');\n"
        "                logContainer.innerHTML = '<div class=\"text-danger\">加载日志失败</div>';\n"
        "            }\n"
        "        });\n",
        "            } else {\n"
        "                console.error('加载日志失败:', data);\n"
        "                const logContainer = document.getElementById('log-container');\n"
        "                logContainer.innerHTML = '<div class=\"text-danger\">加载日志失败</div>';\n"
        "            }\n"
        "        }).catch(function(err) {\n"
        "            console.error('加载日志失败:', err);\n"
        "            const logContainer = document.getElementById('log-container');\n"
        "            logContainer.innerHTML = '<div class=\"text-danger\">加载日志失败</div>';\n"
        "        });\n")

    # GET /api/tasks/<id>/results（后端分页）
    C.rex(r"const url = `/api/tasks/\$\{currentTaskId\}/results\?page=\$\{targetPage\}&per_page=\$\{resultsPerPage\}`;\n"
          r"\n"
          r"        ajaxRequest\(url, 'GET', null, function ?\(err, data\) \{\n"
          r"            const rdata = data\.data \|\| \{\};\n"
          r"            if \(!err && data && Array\.isArray\(rdata\.items\)\) \{",
          "Api.endpoints.task.results(currentTaskId, `page=${targetPage}&per_page=${resultsPerPage}`).then(function(data) {\n"
          "            const rdata = data || {};\n"
          "            if (data && Array.isArray(rdata.items)) {")
    C.rep(
        "                applyResultsFilter();\n"
        "                updateResultsStatistics();\n"
        "                renderResults();\n"
        "            }\n"
        "        });\n",
        "                applyResultsFilter();\n"
        "                updateResultsStatistics();\n"
        "                renderResults();\n"
        "            }\n"
        "        }).catch(function(err) {\n"
        "            console.error('加载任务结果失败:', err);\n"
        "        });\n")

    # GET /api/tasks/<id>/results（CSV 导出用全量拉取；仅 c4 有，错误分支同为“暂无可导出的结果”）
    m = re.search(r"(?P<hind>[ ]*)ajaxRequest\(`/api/tasks/\$\{currentTaskId\}/results`, 'GET', null, function(?P<sp> ?)\(err, data\) \{\n",
                  C.text)
    if m:
        hind, sp = m.group('hind'), m.group('sp')
        body_start = m.end()
        close_rx = re.compile(r"\n" + re.escape(hind) + r"\}\);")
        mc = close_rx.search(C.text, body_start)
        if not mc:
            raise SystemExit('[%s] CSV export close not found' % C.name)
        body = C.text[body_start:mc.start() + 1]
        body = body.replace("const rdata = data.data || {};", "const rdata = data || {};", 1)
        body = body.replace("if (err || !data || !Array.isArray(rdata.items) || rdata.items.length === 0) {",
                            "if (!data || !Array.isArray(rdata.items) || rdata.items.length === 0) {", 1)
        new = (hind + "Api.endpoints.task.results(currentTaskId).then(function" + sp + "(data) {\n"
               + body
               + hind + "}).catch(function" + sp + "() {\n"
               + hind + "    showNotification('暂无可导出的结果', 'warning');\n"
               + hind + "});")
        C.text = C.text[:m.start()] + new + C.text[mc.end():]

    # POST /api/tasks/<id>/cancel
    split_if_else_rebuild(
        C, r"`/api/tasks/\$\{currentTaskId\}/cancel`, 'POST', null",
        "Api.endpoints.task.cancel(currentTaskId)")

    # GET /api/tasks/<id>/status-check（结构特殊：icon 复位 + else 内联）
    m = re.search(r"(?P<hind>[ ]*)ajaxRequest\(`/api/tasks/\$\{currentTaskId\}/status-check`, 'GET', null, function(?P<sp> ?)\(err, data\) \{\n(?P<body>.*?)\n(?P=hind)\}\);",
                  C.text, re.S)
    if not m:
        raise SystemExit('[%s] status-check pattern not found' % C.name)
    hind, sp, body = m.group('hind'), m.group('sp'), m.group('body')
    mi = re.search(r"^(?P<pre>.*?)(?P<i4>[ ]*)if \(!err && data && data\.status === 'success'\) \{\n(?P<success>.*?)\n(?P=i4)\} else \{\n(?P<err>.*?)\n(?P=i4)\}$",
                   body, re.S | re.M)
    if not mi:
        raise SystemExit('[%s] status-check body shape mismatch' % C.name)
    if len(mi.group('i4')) != len(hind) + 4:
        raise SystemExit('[%s] status-check unexpected indent' % C.name)
    success = mi.group('success').replace('data.data.status_check', 'data.status_check')
    err = dedent_n(mi.group('err').replace(
        "showNotification('检查任务状态失败: ' + (data ? data.message : '未知错误'), 'error');",
        "showNotification('检查任务状态失败: 未知错误', 'error');"), 4)
    new = (hind + "Api.endpoints.task.statusCheck(currentTaskId).then(function" + sp + "(data) {\n"
           + mi.group('pre')
           + mi.group('i4') + "if (data && data.status_check) {\n" + success + "\n"
           + mi.group('i4') + "} else {\n" + err + "\n" + mi.group('i4') + "}\n"
           + hind + "}).catch(function" + sp + "(err) {\n"
           + hind + "    icon.style.animation = '';\n"
           + hind + "    btn.disabled = false;\n"
           + hind + "    showNotification('检查任务状态失败: ' + (err && err.message ? err.message : '未知错误'), 'error');\n"
           + hind + "});")
    C.text = C.text[:m.start()] + new + C.text[m.end():]

    # POST /api/tasks/<id>/restart
    split_if_else_rebuild(
        C, r"`/api/tasks/\$\{currentTaskId\}/restart`, 'POST', requestData",
        "Api.endpoints.task.restart(currentTaskId, requestData)")

    # POST /api/tasks/<id>/create-restart
    split_if_else_rebuild(
        C, r"`/api/tasks/\$\{currentTaskId\}/create-restart`, 'POST', \{\}",
        "Api.endpoints.task.createRestart(currentTaskId, {})",
        success_extra=[("data.data.new_task_id", "data.new_task_id")])

    # PUT /api/tasks/<id>/config
    split_if_else_rebuild(
        C, r"`/api/tasks/\$\{currentTaskId\}/config`, 'PUT', requestData",
        "Api.endpoints.task.updateConfig(currentTaskId, requestData)")

    # 导出（文件流，返回原始 Response，同 F2 export.task）
    if ver in ('c5', 'c7'):
        C.rep(
            "const response = await fetch(`/api/exports/tasks/${encodeURIComponent(currentTaskId)}`);",
            "const response = await Api.endpoints.export.task(encodeURIComponent(currentTaskId));")
    if ver == 'c7':
        C.rep(
            "const response = await fetch(`/api/exports/tasks/${encodeURIComponent(currentTaskId)}/stocks`);",
            "const response = await Api.endpoints.export.taskStocks(encodeURIComponent(currentTaskId));")

    C.finish()
    return C.text


def main(keys):
    for key in keys:
        cfg = PAGES[key]
        content, css_inner, js = extract_blocks(cfg)

        # content：url_for → 字面量
        old, new = url_for_replace(cfg['ver'])
        n = content.count(old)
        if n != 1:
            raise SystemExit('[%s] content url_for: found %d' % (key, n))
        content = content.replace(old, new)

        # css（detail 页 scripts 块内的真实 <style>）
        if css_inner is not None and key.endswith('detail'):
            write_crlf('static/css/pages/%s.css' % cfg['page_js'], css_inner + '\n')

        # js：受控改写
        if cfg['kind'] == 'create':
            js = conv_create(cfg, js)
        else:
            js = conv_detail(cfg, js)

        header = (
            "// Google Sheet %s（%s 的页面逻辑）。\n"
            "// 自 %s 内联脚本原样抽离；接口调用经 common/api.js。\n"
            % ('创建任务页（' + cfg['ver'].upper() + '）' if cfg['kind'] == 'create' else '任务详情页（' + cfg['ver'].upper() + '）',
               cfg['src'], cfg['src']))
        js = header + back_link_block(cfg['ver']) + js
        if cfg['ver'] in ('c5', 'c7') and cfg['kind'] == 'detail':
            js = js.replace(back_link_block(cfg['ver']),
                            back_link_block(cfg['ver'])
                            + "\n// 原 JS 模板字符串内的 `{{ version }}`（docs/design/frontend-refactor/03 §5）：\n"
                            "// 静态化后改为运行时读取 query 参数（原服务端渲染值）\n"
                            "const CURRENT_VERSION = new URLSearchParams(location.search).get('version');\n", 1)
        write_crlf('static/js/pages/%s.js' % cfg['page_js'], js)

        # 静态 HTML
        links = [
            '<link href="/static/css/bootstrap.min.css" rel="stylesheet">',
            '<link href="/static/font/bootstrap-icons.css" rel="stylesheet">',
            '<link href="/static/css/template-auth.css" rel="stylesheet">',
            '<link href="/static/css/common/base.css" rel="stylesheet">',
        ]
        if key.endswith('detail'):
            links.append('<link href="/static/css/pages/%s.css" rel="stylesheet">' % cfg['page_js'])
        html = SKELETON.format(title=cfg['title'], links='\n'.join(links), content=content, page_js=cfg['page_js'])
        for bad in ('{{', '{%'):
            if bad in html:
                raise SystemExit('[%s] html leftover jinja' % key)
        write_crlf(cfg['src'], html)


if __name__ == '__main__':
    main(sys.argv[1:])

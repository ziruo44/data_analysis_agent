"""Report loader - reads the final agent report and converts it for frontend display.

Converts absolute filesystem image paths to web-accessible /output/... URLs,
and transforms the full markdown report into HTML.
"""
import os
import re

REPORT_FILENAME = "Agent_Final_Report.md"


def get_report_path(output_folder: str) -> str | None:
    """Return the path to the final report if it exists, else None."""
    report_path = os.path.join(output_folder, REPORT_FILENAME)
    if os.path.exists(report_path):
        return report_path
    return None


def fix_image_paths(content: str) -> str:
    """Convert absolute filesystem image paths to web URLs (/output/...)."""
    def _replace(match):
        alt = match.group(1)
        path = match.group(2).replace("\\", "/")
        if '/output/' in path:
            web_path = '/output/' + path.split('/output/')[-1]
            return f'![{alt}]({web_path})'
        # Relative path like "workflow_xxx/chart.png" — prepend /output/
        if not path.startswith('/') and '://' not in path:
            return f'![{alt}](/output/{path})'
        return match.group(0)

    return re.sub(r'!\[(.+?)\]\((.+?)\)', _replace, content)


def markdown_to_html(text: str) -> str:
    """Convert report markdown to HTML suitable for frontend rendering."""
    lines = text.split('\n')
    out = []
    in_code_block = False
    code_lang = ''
    code_buf = []
    in_ul = False
    in_ol = False
    para_buf = []

    def flush_para():
        if para_buf:
            out.append('<p>' + ' '.join(para_buf) + '</p>')
            para_buf.clear()

    def flush_list():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append('</ul>')
            in_ul = False
        if in_ol:
            out.append('</ol>')
            in_ol = False

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith('```'):
            if in_code_block:
                code_html = '\n'.join(code_buf)
                code_html = code_html.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                lang_attr = f' class="language-{code_lang}"' if code_lang else ''
                out.append(f'<pre><code{lang_attr}>{code_html}</code></pre>')
                in_code_block = False
                code_lang = ''
                code_buf = []
            else:
                flush_para()
                flush_list()
                in_code_block = True
                code_lang = line[3:].strip()
            i += 1
            continue

        if in_code_block:
            code_buf.append(line)
            i += 1
            continue

        if not line.strip():
            flush_para()
            flush_list()
            i += 1
            continue

        if line.startswith('### '):
            flush_para()
            flush_list()
            out.append(f'<h3>{_inline_format(line[4:])}</h3>')
            i += 1
            continue
        if line.startswith('## '):
            flush_para()
            flush_list()
            out.append(f'<h2>{_inline_format(line[3:])}</h2>')
            i += 1
            continue
        if line.startswith('# '):
            flush_para()
            flush_list()
            out.append(f'<h1>{_inline_format(line[2:])}</h1>')
            i += 1
            continue

        img_m = re.match(r'^!\[(.+)\]\((.+)\)$', line)
        if img_m:
            flush_para()
            flush_list()
            img_path = img_m.group(2).replace("\\", "/")
            out.append(f'<img src="{img_path}" alt="{img_m.group(1)}" '
                       f'style="max-width:100%;border-radius:6px;margin:10px 0;">')
            i += 1
            continue

        ul_m = re.match(r'^(\s*)[-*]\s+(.+)$', line)
        if ul_m:
            flush_para()
            if not in_ul:
                out.append('<ul>')
                in_ul = True
            out.append(f'<li>{_inline_format(ul_m.group(2))}</li>')
            i += 1
            continue

        ol_m = re.match(r'^(\s*)\d+\.\s+(.+)$', line)
        if ol_m:
            flush_para()
            if not in_ol:
                out.append('<ol>')
                in_ol = True
            out.append(f'<li>{_inline_format(ol_m.group(2))}</li>')
            i += 1
            continue

        if not in_ul and not in_ol:
            para_buf.append(_inline_format(line))
        i += 1

    flush_para()
    flush_list()

    if in_code_block and code_buf:
        code_html = '\n'.join(code_buf)
        code_html = code_html.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        out.append(f'<pre><code>{code_html}</code></pre>')

    return '\n'.join(out)


def _inline_format(text: str) -> str:
    """Apply inline markdown formatting: bold, italic, inline code."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'<em>\1</em>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text


def split_report_by_turns(content: str) -> dict:
    """Parse the report into per-turn chunks.

    Returns:
        {"header_html": str, "turns": [{"turn_number", "user_prompt", "body_html"}]}
    """
    header_match = re.search(r'^(.*?)(?=## 第 \d+ 轮)', content, re.DOTALL)
    header = header_match.group(1).strip() if header_match else ""

    turn_blocks = re.split(r'\n(?=## 第 \d+ 轮：)', content)

    turns = []
    for block in turn_blocks[1:]:
        m = re.match(r'## 第 (\d+) 轮：(.+)', block)
        if not m:
            continue
        turn_num = int(m.group(1))
        user_prompt = m.group(2).strip()
        body_md = block[m.end():].strip()
        body_fixed = fix_image_paths(body_md)
        body_html = markdown_to_html(body_fixed)

        turns.append({
            "turn_number": turn_num,
            "user_prompt": user_prompt,
            "body_html": body_html,
        })

    return {"header_html": markdown_to_html(fix_image_paths(header)), "turns": turns}


def load_report_html(output_folder: str) -> str | None:
    """Load the final report, fix image paths, and convert to HTML.

    Returns the HTML string or None if the report file doesn't exist.
    """
    report_path = get_report_path(output_folder)
    if not report_path:
        return None
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()
    content = fix_image_paths(content)
    return markdown_to_html(content)

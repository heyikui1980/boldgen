"""生成用于人工验证的 ``.docx`` 测试文档。

不依赖任何第三方库——``.docx`` 本质上就是个 zip，里面放几个 XML。

用途：在 WPS / LibreOffice / Word 里打开，肉眼确认"加粗中文是否变成黑块"。
这是本工具最关键的验收步骤，因为**渲染结果**才是最终标准。

文档里每个字体渲染两行：

* 一行加粗（``w:b``）的中文——这一行在 WPS 出 bug 时会变成涂抹状黑块；
* 一行常规中文——作为对照。

左边用等宽 ASCII 字体标注家族名，方便对照。
"""

from __future__ import annotations

import html
import os
import zipfile
from typing import List, Sequence, Tuple

__all__ = ["build_test_docx", "DEFAULT_SAMPLE"]

#: 默认的中文样本。
DEFAULT_SAMPLE = "中文加粗测试"


def _esc(text: str) -> str:
    return html.escape(text)


def _label_run(text: str) -> str:
    return (
        '<w:r><w:rPr><w:rFonts w:ascii="DejaVu Sans Mono" w:hAnsi="DejaVu Sans Mono" '
        'w:eastAsia="DejaVu Sans Mono" w:cs="DejaVu Sans Mono"/>'
        '<w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr>'
        f'<w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'
    )


def _text_run(text: str, font: str, bold: bool, half_points: int) -> str:
    weight = "<w:b/><w:bCs/>" if bold else ""
    return (
        f'<w:r><w:rPr><w:rFonts w:ascii="{_esc(font)}" w:hAnsi="{_esc(font)}" '
        f'w:eastAsia="{_esc(font)}" w:cs="{_esc(font)}"/>{weight}'
        f'<w:sz w:val="{half_points}"/><w:szCs w:val="{half_points}"/>'
        f'</w:rPr><w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'
    )


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)

_DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="word/styles.xml"/>'
    "</Relationships>"
)

_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:docDefaults><w:rPrDefault><w:rPr>"
    '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="宋体" w:cs="Calibri"/>'
    '<w:sz w:val="21"/><w:szCs w:val="21"/>'
    "</w:rPr></w:rPrDefault>"
    '<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
    "</w:docDefaults>"
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
    "</w:styles>"
)


def build_test_docx(
    path: str,
    families: Sequence[Tuple[str, str]],
    sample: str = DEFAULT_SAMPLE,
    half_points: int = 24,
) -> str:
    """生成测试文档。

    Args:
        path: 输出路径。
        families: ``(显示标签, 字体名)`` 列表。字体名写进 ``w:rFonts``，
            因此需要是**应用能识别的字体名**（与 fontconfig 里的家族名一致）。
        sample: 中文样本文字。
        half_points: 字号（半磅）。

    Returns:
        输出文件路径。
    """
    body: List[str] = []
    body.append(
        "<w:p>" + _label_run("加粗行如果变成一团黑块，说明该字体的假粗渲染有问题")
        + "</w:p>"
    )
    for label, font in families:
        body.append(
            "<w:p>"
            + _label_run(f"[{label} BOLD]")
            + _text_run(sample, font, True, half_points)
            + "</w:p>"
        )
        body.append(
            "<w:p>"
            + _label_run(f"[{label} reg ]")
            + _text_run(sample, font, False, half_points)
            + "</w:p>"
        )

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) +
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )

    out_dir = os.path.dirname(os.path.abspath(path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        archive.writestr("word/styles.xml", _STYLES)
    return path

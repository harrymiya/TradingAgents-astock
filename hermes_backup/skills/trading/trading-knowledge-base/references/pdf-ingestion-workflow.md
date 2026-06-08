# 缠论PDF书籍批量导入知识库的标准化工作流程

## 概述

将缠论/交易相关PDF书籍吸收进 `trading-knowledge-base` skill 的标准流程。

## 先决条件

```bash
cd /home/harrydolly/code/TradingAgents-astock
source .venv/bin/activate
pip install pymupdf pytesseract pillow
```

## 步骤

### 1. 识别PDF类型

```python
import fitz
doc = fitz.open("path/to/book.pdf")
total_text = sum(len(page.get_text()) for page in doc)
has_images = any(page.get_images() for page in doc)
# total_text > 5000 -> 文字版
# total_text < 100 and has_images -> 扫描版需OCR
```

### 2. 提取文字版

```python
def extract_text(filepath, max_pages=0):
    doc = fitz.open(filepath)
    pages = min(max_pages, doc.page_count) if max_pages > 0 else doc.page_count
    texts = [doc[i].get_text() for i in range(pages) if len(doc[i].get_text().strip()) > 30]
    doc.close()
    return texts
```

写入 `books/<书名>.md`。

### 3. OCR扫描版

非root下本地tesseract配置：

```python
os.environ["LD_LIBRARY_PATH"] = "/home/harrydolly/local/tesseract/usr/lib/x86_64-linux-gnu"
os.environ["TESSDATA_PREFIX"] = "/home/harrydolly/local/tesseract/usr/share/tesseract-ocr/5/tessdata"
```

### 4. 去重

用 `f"{size}_{filename}"` 去重键。

### 5. 可编程策略 -> chanlun_screener.py

底分型+底背驰 / 强底分型突破 / 三买v2。

## 注意事项
- OCR速度3-5秒/页，后台跑
- 更新SKILL.md书籍清单

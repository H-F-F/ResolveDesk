from __future__ import annotations

from pathlib import Path

from .domain import RawDocument

try:
    import fitz
except ImportError:
    fitz = None


class DocumentLoader:
    supported_suffixes = {".txt", ".md", ".pdf"}

    @property
    def pdf_supported(self) -> bool:
        return fitz is not None

    def load_directory(self, directory: Path) -> list[RawDocument]:
        documents: list[RawDocument] = []
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in self.supported_suffixes:
                documents.append(self.load_path(path))
        return documents

    def load_path(self, path: Path) -> RawDocument:
        text = self._read_path(path)
        if not text.strip():
            raise ValueError(f"文档内容为空: {path.name}")
        return RawDocument(source=path.name, text=text)

    def load_bytes(self, filename: str, content: bytes) -> RawDocument:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.supported_suffixes:
            raise ValueError(f"暂不支持的文件类型: {suffix}")

        if suffix == ".pdf":
            text = self._read_pdf_bytes(content)
        else:
            text = self._decode_text_bytes(content)

        if not text.strip():
            raise ValueError(f"文档内容为空: {filename}")

        return RawDocument(source=Path(filename).name, text=text)

    def _read_path(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._read_pdf_path(path)
        return self._decode_text_bytes(path.read_bytes())

    def _decode_text_bytes(self, content: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("文本文件编码无法识别，请使用 UTF-8 或 GB18030")

    def _read_pdf_path(self, path: Path) -> str:
        if fitz is None:
            raise ValueError("当前环境未安装 PyMuPDF，无法解析 PDF 文件")
        document = fitz.open(path)
        try:
            return "\n".join(page.get_text("text") for page in document)
        finally:
            document.close()

    def _read_pdf_bytes(self, content: bytes) -> str:
        if fitz is None:
            raise ValueError("当前环境未安装 PyMuPDF，无法解析 PDF 文件")
        document = fitz.open(stream=content, filetype="pdf")
        try:
            return "\n".join(page.get_text("text") for page in document)
        finally:
            document.close()

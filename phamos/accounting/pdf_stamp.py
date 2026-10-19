# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Print the note for the accounting office onto a receipt PDF before it goes to DATEV.

Short notes become a band at the top of page 1: the original page is scaled down a little
so nothing on it is covered. Long notes, and PDFs that cannot be changed (encrypted or
unreadable), get a cover page in front instead. The original file is never modified.
"""

import html
import io
import re

from frappe import _
from frappe.utils import cstr, escape_html, strip_html
from pypdf import PageObject, PdfReader, PdfWriter, Transformation

# The accounting office works in German, whatever language the sender uses.
STAMP_LANGUAGE = "de"
BAND_MAX_LINES = 5
BAND_MAX_CHARS = 420
BAND_HEIGHT_MM = 30
STYLE = """
body { margin: 0; font-family: Helvetica, Arial, sans-serif; color: #1f2937; }
.box { border: 1.5pt solid #d97706; border-radius: 5pt; background: #fffbeb; padding: 5pt 9pt; }
.head { font-weight: bold; color: #b45309; margin-bottom: 2pt; }
"""


def note_to_lines(note):
	"""Plain text lines of a Text Editor value (HTML) or of plain text."""
	text = cstr(note)
	text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", text)
	text = html.unescape(strip_html(text))
	return [line.strip() for line in text.splitlines() if line.strip()]


def note_to_html(text):
	"""Store plain text from the cockpit as paragraphs, the way the Desk editor does."""
	lines = [line.strip() for line in cstr(text).splitlines()]
	return "".join(f"<p>{escape_html(line)}</p>" for line in lines if line)


def stamp_pdf(original, receipt_name, lines):
	"""Return (pdf_bytes, mode) with mode "Band" or "Cover Page"."""
	if len(lines) <= BAND_MAX_LINES and sum(len(line) for line in lines) <= BAND_MAX_CHARS:
		try:
			return _band(original, receipt_name, lines), "Band"
		except Exception:
			pass  # unusual page boxes, encryption, broken files: the cover page always works
	return _cover(original, receipt_name, lines), "Cover Page"


def _block(receipt_name, lines):
	body = "<br>".join(escape_html(line) for line in lines)
	return (
		f"<div class='box'><div class='head'>{escape_html(_('Note for the accounting office', lang=STAMP_LANGUAGE))}"
		f" · {escape_html(receipt_name)}</div><div>{body}</div></div>"
	)


def _render(html_body, page_css):
	"""HTML → PDF with WeasyPrint (a Frappe dependency), which honours exact page sizes."""
	from weasyprint import HTML

	document = f"<html><head><style>@page {{ {page_css} }} {STYLE}</style></head><body>{html_body}</body></html>"
	return HTML(string=document).write_pdf()


def _band(original, receipt_name, lines):
	band_pdf = _render(
		f"<div style='font-size:9pt;margin:4mm 8mm 0 8mm'>{_block(receipt_name, lines)}</div>",
		f"size: 210mm {BAND_HEIGHT_MM}mm; margin: 0",
	)
	band = PdfReader(io.BytesIO(band_pdf)).pages[0]

	reader = _reader(original)
	first = reader.pages[0]
	first.transfer_rotation_to_content()
	box = first.mediabox
	left, bottom = float(box.left), float(box.bottom)
	width, height = float(box.width), float(box.height)

	band_scale = width / float(band.mediabox.width)
	band_height = float(band.mediabox.height) * band_scale
	page_scale = (height - band_height) / height

	page = PageObject.create_blank_page(width=width, height=height)
	page.merge_transformed_page(
		first,
		Transformation()
		.translate(-left, -bottom)
		.scale(page_scale, page_scale)
		.translate((width - width * page_scale) / 2, 0),
	)
	page.merge_transformed_page(band, Transformation().scale(band_scale, band_scale).translate(0, height - band_height))

	writer = PdfWriter()
	writer.add_page(page)
	for other in reader.pages[1:]:
		writer.add_page(other)
	return _bytes(writer)


def _cover(original, receipt_name, lines):
	cover_pdf = _render(f"<div style='font-size:11pt'>{_block(receipt_name, lines)}</div>", "size: A4; margin: 20mm")
	writer = PdfWriter()
	writer.append(PdfReader(io.BytesIO(cover_pdf)))
	writer.append(_reader(original))  # raises for PDFs that cannot be read at all
	return _bytes(writer)


def _reader(content):
	reader = PdfReader(io.BytesIO(content))
	if reader.is_encrypted:
		reader.decrypt("")
	return reader


def _bytes(writer):
	out = io.BytesIO()
	writer.write(out)
	return out.getvalue()

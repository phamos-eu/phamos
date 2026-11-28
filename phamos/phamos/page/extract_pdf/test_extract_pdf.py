import io
import os
import shutil
import unittest

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from phamos.phamos.page.extract_pdf.extract_pdf import (
	UnsupportedFile,
	text_from_pdf,
	value_after_label,
	values_for_lines,
	values_from_file,
	values_from_pdf,
)


class TestValueAfterLabel(unittest.TestCase):
	def test_empty_inputs(self):
		self.assertEqual(value_after_label("", "Invoice No"), "")
		self.assertEqual(value_after_label("Invoice No: INV-1", ""), "")
		self.assertEqual(value_after_label("Invoice No: INV-1", "   "), "")

	def test_colon_dot_or_space_separator(self):
		text = "Invoice No: INV-100\nBill Date. 03.11.2026\nCustomer ACME"
		self.assertEqual(value_after_label(text, "Invoice No"), "INV-100")
		self.assertEqual(value_after_label(text, "Bill Date"), "03.11.2026")
		self.assertEqual(value_after_label(text, "Customer"), "ACME")

	def test_match_is_case_insensitive_and_label_is_trimmed(self):
		self.assertEqual(value_after_label("invoice no: inv-9", "  Invoice No  "), "inv-9")

	def test_label_must_be_a_whole_word(self):
		text = "XInvoice No: SKIP\nInvoice No: KEEP"
		self.assertEqual(value_after_label(text, "Invoice No"), "KEEP")
		self.assertEqual(value_after_label("Proforma Invoice No: INV-2", "Invoice No"), "INV-2")

	def test_regex_characters_in_the_label_are_literal(self):
		self.assertEqual(value_after_label("Invoice (No): 5", "Invoice (No)"), "5")

	def test_first_column_only_when_columns_are_separated(self):
		text = "Invoice No: INV-100  Customer: ACME"
		self.assertEqual(value_after_label(text, "Invoice No"), "INV-100")

	def test_missing_label(self):
		self.assertEqual(value_after_label("Customer: ACME", "Invoice No"), "")

	def test_strips_wrapping_punctuation_from_the_value(self):
		self.assertEqual(value_after_label("Invoice No:: INV-1.", "Invoice No"), "INV-1")


class TestValuesFromPdf(unittest.TestCase):
	def test_reads_each_label_from_the_pdf(self):
		content = _pdf_bytes(["Invoice No: INV-100", "Rechnungsnr. 44", "Customer ACME"])
		self.assertEqual(
			values_from_pdf(content, ["Invoice No", "Rechnungsnr", "Missing"]),
			{"Invoice No": "INV-100", "Rechnungsnr": "44", "Missing": ""},
		)

	def test_no_labels(self):
		content = _pdf_bytes(["Invoice No: INV-100"])
		self.assertEqual(values_from_pdf(content, None), {})
		self.assertEqual(values_from_pdf(content, []), {})


class TestValuesFromFile(unittest.TestCase):
	def test_pdf_uses_the_pdf_reader(self):
		content = _pdf_bytes(["Invoice No: INV-100"])
		self.assertEqual(
			values_from_file(content, ["Invoice No"], "bill.pdf"),
			{"Invoice No": "INV-100"},
		)

	@unittest.skipUnless(shutil.which("tesseract"), "Tesseract is not installed")
	def test_image_uses_tesseract(self):
		content = _png_bytes("Invoice No: INV-100")
		self.assertEqual(
			values_from_file(content, ["Invoice No"], "bill.png"),
			{"Invoice No": "INV-100"},
		)

	def test_other_files_are_rejected(self):
		with self.assertRaises(UnsupportedFile):
			values_from_file(b"not a document", ["Invoice No"], "notes.txt")


class TestValuesForLines(unittest.TestCase):
	def test_business_card_fills_each_target_without_labels(self):
		text = "\n".join(
			[
				"Jane Doe",
				"Acme GmbH",
				"Sales",
				"jane@acme.com",
				"+49 170 1234567",
				"www.acme.com",
				"Hauptstr. 1",
				"10115 Berlin",
			]
		)
		self.assertEqual(
			values_for_lines(
				text,
				[
					{"match_type": "Person", "target_field": "lead_name"},
					{"match_type": "Company", "target_field": "company_name"},
					{"match_type": "Email", "target_field": "email_id"},
					{"match_type": "Phone", "target_field": "mobile_no"},
					{"match_type": "Website", "target_field": "website"},
					{"match_type": "Address", "target_field": "address"},
				],
			),
			[
				"Jane Doe",
				"Acme GmbH",
				"jane@acme.com",
				"+49 170 1234567",
				"www.acme.com",
				"Hauptstr. 1, 10115 Berlin",
			],
		)

	def test_email_on_the_same_line_as_the_name(self):
		text = "Jane Doe jane@acme.com\nAcme GmbH"
		self.assertEqual(
			values_for_lines(
				text,
				[
					{"match_type": "Person", "target_field": "lead_name"},
					{"match_type": "Company", "target_field": "company_name"},
					{"match_type": "Email", "target_field": "email_id"},
				],
			),
			["Jane Doe", "Acme GmbH", "jane@acme.com"],
		)

	def test_second_phone_and_bare_website(self):
		text = "Acme GmbH\n030/1234567\n0176 12345678\nacme.de"
		self.assertEqual(
			values_for_lines(
				text,
				[
					{"match_type": "Phone", "target_field": "phone"},
					{"match_type": "Phone", "target_field": "mobile_no"},
					{"match_type": "Website", "target_field": "website"},
					{"match_type": "Company", "target_field": "company_name"},
				],
			),
			["030/1234567", "0176 12345678", "acme.de", "Acme GmbH"],
		)

	def test_a_date_is_not_a_phone_and_labels_still_work(self):
		text = "Invoice No: INV-100\nBill Date: 03.11.2026\nJane Doe\njane@acme.com"
		self.assertEqual(
			values_for_lines(
				text,
				[
					{"match_type": "Label", "source_label": "Invoice No", "target_field": "bill_no"},
					{"match_type": "Phone", "target_field": "mobile_no"},
					{"match_type": "Email", "target_field": "email_id"},
					{"match_type": "Person", "target_field": "lead_name"},
				],
			),
			["INV-100", "", "jane@acme.com", "Jane Doe"],
		)

	def test_blank_match_type_stays_a_label(self):
		self.assertEqual(
			values_for_lines("Customer: ACME", [{"source_label": "Customer", "target_field": "customer"}]),
			["ACME"],
		)

	def test_company_uses_the_first_line_when_no_person_is_mapped(self):
		text = "Acme GmbH\njane@acme.com"
		self.assertEqual(
			values_for_lines(text, [{"match_type": "Company", "target_field": "customer_name"}]),
			["Acme GmbH"],
		)

	def test_unknown_match_type_is_read_as_a_label(self):
		self.assertEqual(
			values_for_lines(
				"Customer: ACME",
				[{"match_type": "Something else", "source_label": "Customer", "target_field": "customer"}],
			),
			["ACME"],
		)

	def test_no_lines(self):
		self.assertEqual(values_for_lines("Jane Doe", None), [])
		self.assertEqual(values_for_lines("Jane Doe", []), [])

	def test_card_lines_are_read_from_pdf_text(self):
		content = _pdf_bytes(
			[
				"Jane Doe",
				"Acme GmbH",
				"jane@acme.com",
				"+49 170 1234567",
				"www.acme.com",
			]
		)
		self.assertEqual(
			values_for_lines(
				text_from_pdf(content),
				[
					{"match_type": "Person", "target_field": "lead_name"},
					{"match_type": "Company", "target_field": "company_name"},
					{"match_type": "Email", "target_field": "email_id"},
					{"match_type": "Phone", "target_field": "mobile_no"},
					{"match_type": "Website", "target_field": "website"},
				],
			),
			["Jane Doe", "Acme GmbH", "jane@acme.com", "+49 170 1234567", "www.acme.com"],
		)


def _pdf_bytes(lines):
	writer = PdfWriter()
	page = writer.add_blank_page(width=612, height=792)
	font = DictionaryObject(
		{
			NameObject("/Type"): NameObject("/Font"),
			NameObject("/Subtype"): NameObject("/Type1"),
			NameObject("/BaseFont"): NameObject("/Helvetica"),
		}
	)
	page[NameObject("/Resources")] = DictionaryObject(
		{NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
	)
	commands = ["BT /F1 12 Tf 72 720 Td"]
	for index, line in enumerate(lines):
		if index:
			commands.append("0 -18 Td")
		commands.append("(" + _pdf_text(line) + ") Tj")
	commands.append("ET")
	stream = DecodedStreamObject()
	stream.set_data(" ".join(commands).encode("latin-1"))
	page[NameObject("/Contents")] = writer._add_object(stream)
	buffer = io.BytesIO()
	writer.write(buffer)
	return buffer.getvalue()


def _pdf_text(value):
	return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _png_bytes(text):
	font_path = next(
		(
			path
			for path in (
				"/System/Library/Fonts/Supplemental/Arial.ttf",
				"/Library/Fonts/Arial.ttf",
				"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
			)
			if os.path.exists(path)
		),
		None,
	)
	if not font_path:
		raise unittest.SkipTest("No font available for the image test")
	image = Image.new("RGB", (900, 220), "white")
	ImageDraw.Draw(image).text((24, 70), text, fill="black", font=ImageFont.truetype(font_path, 48))
	buffer = io.BytesIO()
	image.save(buffer, format="PNG")
	return buffer.getvalue()


if __name__ == "__main__":
	unittest.main()

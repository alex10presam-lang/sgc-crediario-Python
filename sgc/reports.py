import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sgc.money import brl


def payment_pdf(details):
    """The caller obtains details through the tenant-aware service first."""
    stream = io.BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=44,
        leftMargin=44,
        topMargin=44,
        bottomMargin=44,
        title=f"Recebimento SGC {details['id']}",
    )
    text = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=10,
        leading=16,
        textColor=colors.HexColor("#243a34"),
    )
    heading = ParagraphStyle(
        "heading", parent=text, fontName="Helvetica-Bold", fontSize=26, leading=32
    )
    small = ParagraphStyle("small", parent=text, fontSize=8, leading=12)

    def safe(value):
        return escape(str(value))

    content = [
        Paragraph("SGC / CREDIÁRIO", small),
        Spacer(1, 14),
        Paragraph("Comprovante de recebimento", heading),
        Spacer(1, 16),
    ]
    for line in [
        f"Empresa: {safe(details['company'])}",
        f"Recebimento #{details['id']} · Venda #{details['sale_id']}",
        f"Data: {details['date'].strftime('%d/%m/%Y %H:%M')}",
        f"Cliente: {safe(details['customer'])}",
        f"Descrição: {safe(details['description'])}",
    ]:
        content.append(Paragraph(line, text))
    content.extend(
        [
            Spacer(1, 24),
            Paragraph("VALOR REGISTRADO", small),
            Paragraph(brl(details["amount"]), heading),
            Spacer(1, 20),
        ]
    )
    rows = [["Parcela", "Valor destinado"]] + [
        [
            str(row["number"]) if row["number"] else "Entrada / à vista",
            brl(row["amount"]),
        ]
        for row in details["allocations"]
    ]
    table = Table(rows, colWidths=[250, 170], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243a34")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#cad5cc")),
            ]
        )
    )
    content += [
        table,
        Spacer(1, 24),
        Paragraph("SITUAÇÃO: " + ("ESTORNADO" if details["reversed"] else "REGISTRADO"), text),
        Spacer(1, 18),
        Paragraph(
            "Demonstração local de portfólio. Documento sem validade fiscal; não há integração bancária nem confirmação externa de pagamento.",
            small,
        ),
    ]
    document.build(content)
    return stream.getvalue()

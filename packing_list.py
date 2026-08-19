from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
import base64
import html
import re
from typing import BinaryIO, Iterable

import pdfplumber
import qrcode
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


INSTALLATION_URL = (
    "https://bostonaestheticsus-my.sharepoint.com/:v:/g/personal/"
    "brandon_acosta_bostonaesthetics_com/IQBzp1k2UQ-GQq00bctNXZZaAVaP_pnTV7AYq4GCEC25f8k"
)
DELIVERY_EMAIL = "brandon.acosta@bostonaesthetics.com"
GREEN = colors.HexColor("#39B54A")
GREEN_DARK = colors.HexColor("#258D36")
INK = colors.HexColor("#171A18")
MUTED = colors.HexColor("#69716B")
LINE = colors.HexColor("#DCE3DC")
GREEN_SOFT = colors.HexColor("#EEF9EF")


BUNDLE_ITEMS = [
    {"name": "ZenTite Unicorn+", "description": "Device controller - device SN", "quantity": 1},
    {"name": "MicroRF Handpiece", "description": "Included with ZenTite system", "quantity": 1},
    {"name": "Pure+ Handpiece", "description": "Included with ZenTite system", "quantity": 1},
    {"name": "Pure+ B1 Tip", "description": "Included accessory", "quantity": 1},
    {"name": "Foot Switch", "description": "Included accessory", "quantity": 1},
    {"name": "Power Cord", "description": "Included accessory", "quantity": 1},
    {"name": "Power Cord Fastener (with 2 screws)", "description": "Included hardware", "quantity": 1},
    {"name": "Screwdriver", "description": "Included tool", "quantity": 1},
    {"name": "Fuse", "description": "Included spare", "quantity": 4},
    {"name": "Handpiece Holder", "description": "Included accessory", "quantity": 2},
    {"name": "Connector", "description": "Included accessory", "quantity": 1},
    {"name": "User Manual", "description": "Included documentation", "quantity": 1},
    {"name": "Treatment Guide", "description": "Included documentation", "quantity": 1},
    {"name": "Trolley", "description": "Included equipment", "quantity": 1},
    {"name": "Cable Hanger", "description": "Included accessory", "quantity": 2},
    {"name": "Return Pad", "description": "Included when Pure+ handpiece is present", "quantity": 1},
]


def blank_order() -> dict:
    return {
        "customer": "",
        "address": "",
        "invoice_number": "",
        "invoice_date": "",
        "ship_date": "",
        "delivery_date": "",
        "carrier": "",
        "tracking": "",
        "device_serial": "",
        "notes": "",
        "items": [],
    }


def demo_order() -> dict:
    order = {
        **blank_order(),
        "customer": "Medrino LLC",
        "address": "100 S Baylen St Ste E\nPensacola, FL 32502-5825",
        "invoice_number": "BA-2608-004",
        "invoice_date": "08/18/2026",
        "ship_date": "08/18/2026",
        "delivery_date": "08/21/2026",
        "carrier": "Aeronet",
        "tracking": "DEMO-TRACKING-123",
        "device_serial": "US01FS508AA57",
        "items": [
            _item("ZenTite RF System", "SN: US01FS508AA57", 1, "QBO"),
            _item("ZenTite Unicorn+", "QuickBooks bundle component", 1, "QBO"),
            _item("Handpiece MicroRF", "QuickBooks bundle component", 1, "QBO"),
            _item("Handpiece Pure +", "QuickBooks bundle component", 1, "QBO"),
            _item("MicroRF 25N", "QuickBooks line item", 1, "QBO"),
            _item("MicroRF 49", "QuickBooks line item", 1, "QBO"),
            _item("MicroRF 9N", "QuickBooks line item", 1, "QBO"),
        ],
    }
    return enrich_zentite_bundle(order)


def _item(name: str, description: str, quantity: int, source: str, serial: str = "") -> dict:
    return {
        "name": name,
        "description": description,
        "quantity": int(quantity),
        "serial": serial,
        "source": source,
    }


def canonical_name(value: str) -> str:
    name = re.sub(r"[^a-z0-9+]", "", (value or "").lower())
    if re.search(r"zentite.*rf.*system|zentitesystem", name):
        return "zentite-system"
    if re.search(r"unicorn\+?", name):
        return "unicorn-plus"
    if re.search(r"microrf.*(?:hp|handpiece)|handpiece.*microrf", name):
        return "microrf-handpiece"
    if re.search(r"pure\+?.*(?:hp|handpiece)|handpiece.*pure\+?", name):
        return "pure-plus-handpiece"
    aliases = {
        "pure+b1tip": "pure-plus-b1-tip",
        "footswitch": "foot-switch",
        "powercordfastenerwith2screws": "power-cord-fastener",
        "powercordfastener": "power-cord-fastener",
        "powercord": "power-cord",
        "screwdriver": "screwdriver",
        "fuse": "fuse",
        "handpieceholder": "handpiece-holder",
        "connector": "connector",
        "usermanual": "user-manual",
        "treatmentguide": "treatment-guide",
        "trolley": "trolley",
        "cablehanger": "cable-hanger",
        "returnpad": "return-pad",
    }
    return aliases.get(name, name)


def extract_serial_or_lot(description: str) -> str:
    """Promote an SN or lot entered in the QBO description into the printable field."""
    match = re.search(r"\b(?:S/?N|SERIAL|LOT)\s*(?:NO\.?|NUMBER|#)?\s*:?\s*(.+?)\s*$", description or "", re.I)
    return match.group(1).strip() if match else ""


def is_zentite(order: dict) -> bool:
    return any(canonical_name(item.get("name", "")) == "zentite-system" for item in order.get("items", []))


def enrich_zentite_bundle(order: dict, force: bool = False) -> dict:
    result = deepcopy(order)
    if not force and not is_zentite(result):
        return result

    existing = {canonical_name(item.get("name", "")) for item in result["items"]}
    pure_present = (
        force
        or "pure-plus-handpiece" in existing
        or "zentite-system" in existing
    )
    for bundle_item in BUNDLE_ITEMS:
        canonical = canonical_name(bundle_item["name"])
        if canonical == "return-pad" and not pure_present:
            continue
        if canonical in existing:
            continue
        serial = result.get("device_serial", "") if canonical == "unicorn-plus" else ""
        result["items"].append(_item(**bundle_item, source="ZenTite bundle", serial=serial))
        existing.add(canonical)
    return result


def _group_rows(words: Iterable[dict], tolerance: float = 2.5) -> list[dict]:
    rows: list[dict] = []
    for word in sorted(words, key=lambda word: (word["top"], word["x0"])):
        row = next((candidate for candidate in rows if abs(candidate["top"] - word["top"]) <= tolerance), None)
        if row:
            row["words"].append(word)
            row["top"] = (row["top"] + word["top"]) / 2
        else:
            rows.append({"top": word["top"], "words": [word]})
    for row in rows:
        row["words"].sort(key=lambda word: word["x0"])
        row["text"] = " ".join(word["text"] for word in row["words"]).strip()
    return sorted(rows, key=lambda row: row["top"])


def _row_label(row: dict, label: str) -> bool:
    return bool(re.match(rf"^{re.escape(label)}(?:\s|$)", row["text"], re.I))


def _right_of_label(rows: list[dict], label_pattern: str) -> str:
    pattern = re.compile(label_pattern, re.I)
    for row in rows:
        match = pattern.search(row["text"])
        if match:
            return (match.group(1) or "").strip()
    return ""


def _extract_ship_to(rows: list[dict]) -> tuple[str, str]:
    label_row = None
    label_index = -1
    for row in rows:
        tokens = [word["text"].upper() for word in row["words"]]
        for index in range(len(tokens) - 1):
            if tokens[index:index + 2] == ["SHIP", "TO"]:
                label_row = row
                label_index = index
                break
        if label_row:
            break
    if not label_row or label_index < 0:
        return "", ""
    ship_words = label_row["words"][label_index:label_index + 2]
    left = ship_words[0]["x0"] - 4
    invoice_word = next(
        (word for word in label_row["words"] if word["x0"] > left and word["text"].upper() == "INVOICE"),
        None,
    )
    right = invoice_word["x0"] - 10 if invoice_word else left + 220
    lines: list[str] = []
    for row in rows:
        if row["top"] <= label_row["top"] + 3 or row["top"] > label_row["top"] + 95:
            continue
        selected = [word["text"] for word in row["words"] if left <= word["x0"] < right]
        line = " ".join(selected).strip()
        if not line:
            continue
        if re.match(r"^(?:SERVICE|PRODUCT|DESCRIPTION|QTY|QUANTITY)\b", line, re.I):
            break
        lines.append(line)
    return (lines[0] if lines else "", "\n".join(lines[1:5]))


def _extract_items(rows: list[dict]) -> list[dict]:
    header = next(
        (
            row
            for row in rows
            if re.search(r"\b(?:SERVICE|PRODUCT|ITEM)\b", row["text"], re.I)
            and re.search(r"\bDESCRIPTION\b", row["text"], re.I)
            and re.search(r"\b(?:QTY|QUANTITY)\b", row["text"], re.I)
        ),
        None,
    )
    if not header:
        return []
    description_word = next(word for word in header["words"] if re.match(r"DESCRIPTION", word["text"], re.I))
    quantity_word = next(word for word in header["words"] if re.match(r"QTY|QUANTITY", word["text"], re.I))
    description_x = description_word["x0"]
    quantity_x = quantity_word["x0"]
    items: list[dict] = []
    for row in rows:
        if row["top"] <= header["top"] + 3:
            continue
        if re.search(r"\b(?:SUBTOTAL|TOTAL|BALANCE DUE)\b", row["text"], re.I):
            break
        quantity_candidates = [
            word for word in row["words"]
            if abs(word["x0"] - quantity_x) <= 35 and re.fullmatch(r"\d+(?:\.\d+)?", word["text"].replace(",", ""))
        ]
        if not quantity_candidates:
            continue
        name = " ".join(word["text"] for word in row["words"] if word["x0"] < description_x - 4).strip()
        if not name:
            continue
        description = " ".join(
            word["text"] for word in row["words"]
            if description_x - 4 <= word["x0"] < quantity_x - 4
        ).strip()
        items.append(
            _item(
                name=name,
                description=description or "QuickBooks line item",
                quantity=max(1, int(float(quantity_candidates[-1]["text"].replace(",", "")))),
                source="QBO",
                serial=extract_serial_or_lot(description),
            )
        )
    return items


def parse_qbo_pdf(source: bytes | BinaryIO) -> dict:
    stream = BytesIO(source) if isinstance(source, bytes) else source
    with pdfplumber.open(stream) as pdf:
        words: list[dict] = []
        for page_number, page in enumerate(pdf.pages, start=1):
            for word in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                words.append({**word, "page": page_number})
    first_page = [word for word in words if word["page"] == 1]
    rows = _group_rows(first_page)
    customer, address = _extract_ship_to(rows)
    items = _extract_items(rows)
    unicorn_serial = next(
        (item["serial"] for item in items if canonical_name(item["name"]) == "unicorn-plus" and item["serial"]),
        "",
    )
    system_serial = next(
        (item["serial"] for item in items if canonical_name(item["name"]) == "zentite-system" and item["serial"]),
        "",
    )
    for item in items:
        if canonical_name(item["name"]) == "zentite-system":
            item["serial"] = ""
    order = {
        **blank_order(),
        "customer": customer,
        "address": address,
        "invoice_number": _right_of_label(rows, r"\bINVOICE(?:\s+(?:NO\.?|NUMBER|#))?\s+([^\s]+)\s*$"),
        "invoice_date": _right_of_label(rows, r"\bDATE\s+([^\s]+)\s*$"),
        "ship_date": _right_of_label(rows, r"\bSHIP(?:PED)?\s+DATE\s+([^\s]+)\s*$"),
        "delivery_date": _right_of_label(rows, r"\b(?:(?:EXPECTED|ESTIMATED)\s+)?DELIVERY\s+DATE\s+([^\s]+)\s*$"),
        "carrier": _right_of_label(rows, r"\b(?:CARRIER|SHIP\s+VIA|SHIPPING\s+METHOD)\s+(.+)$"),
        "tracking": _right_of_label(rows, r"\bTRACKING(?:\s+(?:NO\.?|NUMBER|#))?\s+([^\s]+)\s*$"),
        "device_serial": unicorn_serial or system_serial,
        "items": items,
    }
    return enrich_zentite_bundle(order)


def sync_device_serial(order: dict) -> dict:
    result = deepcopy(order)
    for item in result.get("items", []):
        canonical = canonical_name(item.get("name", ""))
        promoted_value = item.get("serial", "") or extract_serial_or_lot(item.get("description", ""))
        if canonical == "unicorn-plus":
            if not result.get("device_serial") and promoted_value:
                result["device_serial"] = promoted_value
            item["serial"] = result.get("device_serial", "") or promoted_value
        elif canonical == "zentite-system":
            item["serial"] = ""
        elif not item.get("serial") and promoted_value:
            item["serial"] = promoted_value
    return result


def email_subject(order: dict) -> str:
    suffix = f" | Invoice {order['invoice_number']}" if order.get("invoice_number") else ""
    return f"Your Boston Aesthetics shipment{suffix}"


def email_text(order: dict) -> str:
    greeting = f"Hello {order['customer']}," if order.get("customer") else "Hello,"
    facts = [
        order.get("invoice_number") and f"Invoice: {order['invoice_number']}",
        order.get("invoice_date") and f"Invoice date: {order['invoice_date']}",
        order.get("ship_date") and f"Ship date: {order['ship_date']}",
        order.get("delivery_date") and f"Expected delivery: {order['delivery_date']}",
        order.get("carrier") and f"Carrier: {order['carrier']}",
        order.get("tracking") and f"Tracking number: {order['tracking']}",
        order.get("device_serial") and f"ZenTite / Unicorn+ device SN: {order['device_serial']}",
    ]
    content_lines = []
    for item in order.get("items", []):
        serial = order.get("device_serial", "") if canonical_name(item["name"]) == "unicorn-plus" else item.get("serial", "")
        serial_text = f" - SN/Lot {serial}" if serial else ""
        content_lines.append(f"- {item['name']} - Qty {item['quantity']}{serial_text}")
    return "\n".join(
        [
            greeting,
            "",
            "Good news - your Boston Aesthetics order is on its way. We have included the important details below so everything is easy to find.",
            "",
            *[fact for fact in facts if fact],
            "",
            "Ship to:",
            order.get("customer", ""),
            order.get("address", ""),
            "",
            "Shipment contents:",
            *content_lines,
            "",
            order.get("notes") or "Please inspect the shipment upon arrival and retain the packing list for your records.",
            "",
            "ZenTite installation video:",
            INSTALLATION_URL,
            "",
            f"Questions about delivery? Contact {DELIVERY_EMAIL}.",
            "",
            "Boston Aesthetics Inc.",
            "1 Peters Canyon Rd, Suite 100",
            "Irvine, CA 92606",
        ]
    )


def _email_logo_data_uri(logo_path: str | Path | None) -> str:
    if not logo_path:
        return ""
    with Image.open(logo_path) as image:
        converted = image.convert("RGBA")
        output = BytesIO()
        converted.save(output, format="PNG", optimize=True)
    return f"data:image/png;base64,{base64.b64encode(output.getvalue()).decode('ascii')}"


def _installation_qr_data_uri() -> str:
    qr_image = qrcode.make(INSTALLATION_URL)
    output = BytesIO()
    qr_image.save(output, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(output.getvalue()).decode('ascii')}"


def email_html(order: dict, logo_path: str | Path | None = None) -> str:
    esc = lambda value: html.escape(str(value or ""), quote=True)
    forest = "#173D2B"
    forest_deep = "#0F2D20"
    sage = "#EDF4ED"
    ivory = "#F6F3EC"
    gold = "#B69A61"
    logo_uri = _email_logo_data_uri(logo_path)
    qr_uri = _installation_qr_data_uri()
    logo = (
        f'<img src="{logo_uri}" width="205" alt="Boston Aesthetics" style="display:block;width:205px;max-width:100%;height:auto;margin:0 auto;border:0;">'
        if logo_uri
        else '<div style="color:#39b54a;font-size:24px;font-weight:700;">Boston Aesthetics</div>'
    )
    facts = [
        ("Invoice number", order.get("invoice_number")),
        ("Ship date", order.get("ship_date")),
        ("Expected delivery", order.get("delivery_date")),
        ("Carrier", order.get("carrier")),
        ("Tracking number", order.get("tracking")),
        ("ZenTite device SN", order.get("device_serial")),
    ]
    fact_rows = "".join(
        f'<tr><td class="fact-cell fact-label copy-muted line-border" width="44%" style="padding:12px 16px;border-bottom:1px solid #D7E2D8;color:#637067;font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;">{esc(label)}</td>'
        f'<td class="fact-cell fact-value copy-primary line-border" style="padding:12px 16px;border-bottom:1px solid #D7E2D8;color:{forest_deep};font-size:14px;font-weight:700;line-height:1.35;text-align:right;word-break:break-word;">{esc(value)}</td></tr>'
        for label, value in facts if value
    )
    item_rows = ""
    for item in order.get("items", []):
        serial = order.get("device_serial", "") if canonical_name(item["name"]) == "unicorn-plus" else item.get("serial", "")
        item_rows += (
            f'<tr><td class="item-cell item-name copy-primary line-border" bgcolor="#FFFFFF" style="padding:11px 12px;border-bottom:1px solid #E3E9E3;background:#FFFFFF;color:#24372B;font-size:13px;line-height:1.4;">{esc(item["name"])}</td>'
            f'<td class="item-cell item-value copy-muted line-border" bgcolor="#FFFFFF" style="padding:11px 12px;border-bottom:1px solid #E3E9E3;background:#FFFFFF;color:#657067;font-size:12px;line-height:1.4;word-break:break-word;">{esc(serial or "-")}</td>'
            f'<td class="item-cell item-value copy-primary line-border" bgcolor="#FFFFFF" style="padding:11px 8px;border-bottom:1px solid #E3E9E3;background:#FFFFFF;color:{forest_deep};font-size:13px;font-weight:700;text-align:center;">{int(item["quantity"])}</td></tr>'
        )
    notes = (
        f'<table class="notes" role="presentation" cellpadding="0" cellspacing="0" width="100%" bgcolor="{ivory}" style="margin:0;background:{ivory};border-collapse:collapse;border-left:4px solid {gold};"><tr><td class="copy-muted" style="padding:16px 18px;color:#59665D;font-size:13px;line-height:1.65;"><strong class="copy-primary" style="display:block;margin-bottom:4px;color:{forest_deep};font-size:13px;">A note for delivery</strong>{esc(order["notes"])}</td></tr></table>'
        if order.get("notes") else ""
    )
    setup_callout = ""
    if is_zentite(order):
        setup_callout = f'''<tr><td class="content-pad" style="padding:0 44px 30px;">
          <table class="setup-card" role="presentation" cellpadding="0" cellspacing="0" width="100%" bgcolor="{sage}" style="background:{sage};border-collapse:collapse;border-left:4px solid {gold};">
            <tr><td class="qr-cell" width="118" valign="middle" align="center" style="padding:20px 14px 20px 20px;"><a href="{INSTALLATION_URL}" aria-label="Open the ZenTite installation video" style="text-decoration:none;"><img src="{qr_uri}" width="86" height="86" alt="Scan to open the ZenTite installation video" style="display:block;width:86px;height:86px;margin:0 auto;border:7px solid #FFFFFF;"></a></td>
            <td class="setup-copy" valign="middle" style="padding:20px 22px 20px 4px;"><div class="section-label" style="color:{gold};font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">ZenTite installation</div><div class="copy-primary" style="margin:7px 0;color:{forest_deep};font-family:Georgia,'Times New Roman',serif;font-size:22px;line-height:1.25;">Let's get you set up</div><div class="copy-muted" style="color:#5F6D63;font-size:13px;line-height:1.6;">Scan the QR code or use the button below for a guided installation walkthrough.</div><div style="margin-top:14px;"><a class="setup-button" href="{INSTALLATION_URL}" style="display:inline-block;padding:11px 17px;background:{forest};border-radius:3px;color:#FFFFFF;text-decoration:none;font-size:11px;font-weight:700;letter-spacing:.5px;">OPEN INSTALLATION VIDEO</a></div></td></tr>
          </table>
        </td></tr>'''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="x-apple-disable-message-reformatting"><meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<style>
  :root {{ color-scheme: light dark; supported-color-schemes: light dark; }}
  html, body {{ width:100% !important; margin:0 !important; padding:0 !important; }}
  body {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
  table, td {{ border-collapse:collapse; mso-table-lspace:0pt; mso-table-rspace:0pt; }}
  img {{ border:0; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic; }}
  a[x-apple-data-detectors] {{ color:inherit !important; text-decoration:none !important; }}
  @media only screen and (max-width:600px) {{
    .email-bg {{ padding:0 !important; }}
    .email-card {{ width:100% !important; max-width:100% !important; }}
    .content-pad {{ padding-left:22px !important; padding-right:22px !important; }}
    .hero-title {{ font-size:27px !important; line-height:1.22 !important; }}
    .hero-copy {{ font-size:15px !important; line-height:1.65 !important; }}
    .qr-cell, .setup-copy {{ display:block !important; width:auto !important; text-align:center !important; }}
    .qr-cell {{ padding:20px 20px 8px !important; }}
    .setup-copy {{ padding:6px 22px 22px !important; }}
    .fact-cell {{ padding:11px 12px !important; }}
    .fact-label {{ font-size:10px !important; }}
    .fact-value {{ font-size:13px !important; }}
    .item-cell {{ padding:10px 8px !important; font-size:11px !important; }}
    .item-name {{ font-size:12px !important; }}
  }}
  @media (prefers-color-scheme: dark) {{
    body, .email-bg {{ background:#07170F !important; color:#F5F2E9 !important; }}
    .email-card {{ background:#10271A !important; }}
    .copy-primary {{ color:#F7F4ED !important; }}
    .copy-muted {{ color:#CCD7CE !important; }}
    .soft-card, .facts, .setup-card, .notes {{ background:#193624 !important; }}
    .fact-cell, .item-cell {{ background:#10271A !important; }}
    .line-border {{ border-color:#34523E !important; }}
    .logo-shell {{ background:#FFFFFF !important; }}
    .footer-copy {{ color:#C8D2CA !important; }}
    .setup-button {{ background:#2D7F44 !important; color:#FFFFFF !important; }}
  }}
  [data-ogsc] .email-bg {{ background:#07170F !important; }}
  [data-ogsc] .email-card {{ background:#10271A !important; }}
  [data-ogsc] .copy-primary {{ color:#F7F4ED !important; }}
  [data-ogsc] .copy-muted {{ color:#CCD7CE !important; }}
  [data-ogsc] .soft-card, [data-ogsc] .facts, [data-ogsc] .setup-card, [data-ogsc] .notes {{ background:#193624 !important; }}
  [data-ogsc] .fact-cell, [data-ogsc] .item-cell {{ background:#10271A !important; }}
  [data-ogsc] .line-border {{ border-color:#34523E !important; }}
  [data-ogsc] .logo-shell {{ background:#FFFFFF !important; }}
</style></head>
<body class="email-bg" style="margin:0;background:{ivory};padding:0;font-family:Arial,Helvetica,sans-serif;color:#24372B;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">Your Boston Aesthetics shipment is on the way. Tracking and delivery details are inside.</div>
  <div class="email-bg" style="margin:0;background:{ivory};padding:34px 12px;font-family:Arial,Helvetica,sans-serif;color:#24372B;">
    <table class="email-card" role="presentation" aria-label="Boston Aesthetics shipment update" cellpadding="0" cellspacing="0" width="100%" bgcolor="#FFFFFF" style="width:100%;max-width:640px;margin:0 auto;background:#FFFFFF;border-collapse:collapse;border-top:8px solid {forest};">
      <tr><td class="content-pad" align="center" style="padding:28px 44px 22px;"><div class="logo-shell" style="display:inline-block;padding:10px 18px;background:#FFFFFF;border-radius:6px;">{logo}</div></td></tr>
      <tr><td class="content-pad" style="padding:0 44px 30px;text-align:center;"><div class="section-label" style="margin:0 0 10px;color:{gold};font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;">Shipment update</div><h1 class="hero-title copy-primary" style="margin:0;color:{forest};font-family:Georgia,'Times New Roman',serif;font-size:32px;font-weight:400;line-height:1.2;">Good news - it's headed your way</h1><p class="hero-copy copy-muted" style="margin:16px auto 0;max-width:500px;color:#647168;font-size:15px;line-height:1.65;">Hello{f' {esc(order.get("customer"))} team' if order.get('customer') else ''}, your Boston Aesthetics order has shipped. Here are the details you may want along the way.</p></td></tr>
      <tr><td class="content-pad" style="padding:0 44px 30px;"><div class="section-label" style="margin-bottom:10px;color:{gold};font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">Delivery at a glance</div><table class="facts soft-card" role="presentation" cellpadding="0" cellspacing="0" width="100%" bgcolor="{sage}" style="background:{sage};border-collapse:collapse;">{fact_rows}</table></td></tr>
      <tr><td class="content-pad" style="padding:0 44px 30px;"><table class="soft-card" role="presentation" cellpadding="0" cellspacing="0" width="100%" bgcolor="{ivory}" style="background:{ivory};border-collapse:collapse;"><tr><td style="padding:18px 20px;"><div class="section-label" style="margin-bottom:7px;color:{gold};font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">Delivering to</div><div class="copy-primary" style="color:{forest_deep};font-family:Georgia,'Times New Roman',serif;font-size:20px;line-height:1.3;">{esc(order.get('customer') or 'Company name')}</div><div class="copy-muted" style="margin-top:7px;color:#627067;font-size:13px;line-height:1.65;white-space:pre-line;">{esc(order.get('address') or 'Ship To address')}</div></td></tr></table></td></tr>
      {setup_callout}
      <tr><td class="content-pad" style="padding:0 44px 30px;"><div class="section-label" style="margin-bottom:5px;color:{gold};font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">Inside your shipment</div><div class="copy-muted" style="margin:0 0 12px;color:#627067;font-size:13px;line-height:1.5;">{len(order.get('items', []))} line items are included in this shipment.</div><table class="item-table" role="table" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;border-top:2px solid {forest};"><tr style="background:{forest};"><th style="padding:11px 12px;color:#FFFFFF;font-size:10px;letter-spacing:.8px;text-align:left;">ITEM</th><th style="padding:11px 12px;color:#FFFFFF;font-size:10px;letter-spacing:.8px;text-align:left;">SERIAL / LOT</th><th width="48" style="padding:11px 8px;color:#FFFFFF;font-size:10px;letter-spacing:.8px;text-align:center;">QTY</th></tr>{item_rows}</table></td></tr>
      <tr><td class="content-pad" style="padding:0 44px 34px;">{notes}</td></tr>
      <tr><td class="footer-copy" style="padding:27px 44px;background:{forest_deep};color:#DCE6DE;font-size:11px;line-height:1.7;text-align:center;"><div style="margin-bottom:6px;color:#FFFFFF;font-family:Georgia,'Times New Roman',serif;font-size:17px;">Questions? We're happy to help.</div><a href="mailto:{DELIVERY_EMAIL}" style="color:#BFDCC4;text-decoration:none;font-size:12px;font-weight:700;">{DELIVERY_EMAIL}</a><div style="margin-top:14px;color:#9FB0A4;">Boston Aesthetics Inc. &nbsp;|&nbsp; Irvine, California</div></td></tr>
    </table>
  </div>
</body></html>'''


def _fit_text(value: str, font: str, size: float, max_width: float) -> str:
    value = str(value or "")
    if stringWidth(value, font, size) <= max_width:
        return value
    shortened = value
    while shortened and stringWidth(shortened + "...", font, size) > max_width:
        shortened = shortened[:-1]
    return shortened + "..."


def _wrap(value: str, font: str, size: float, max_width: float, max_lines: int = 4) -> list[str]:
    lines: list[str] = []
    for paragraph in str(value or "").splitlines() or [""]:
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and stringWidth(candidate, font, size) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit_text(lines[-1], font, size, max_width)
    return lines


def build_packing_list_pdf(order: dict, logo_path: str | Path) -> bytes:
    order = sync_device_serial(order)
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, pageCompression=1)
    width, height = letter
    items = order.get("items", []) or [_item("Shipment item", "", 1, "Manual")]
    page_size = 23
    chunks = [items[index:index + page_size] for index in range(0, len(items), page_size)]

    for page_index, chunk in enumerate(chunks):
        first_page = page_index == 0
        last_page = page_index == len(chunks) - 1
        pdf.setFillColor(colors.white)
        pdf.rect(0, 0, width, height, stroke=0, fill=1)
        pdf.drawImage(ImageReader(str(logo_path)), 38, 712, width=170, height=51.6, preserveAspectRatio=True, mask="auto")
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica", 24)
        pdf.drawRightString(574, 742, "PACKING LIST")
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawRightString(574, 726, f"INVOICE {order.get('invoice_number') or 'PENDING'}")
        pdf.setStrokeColor(LINE)
        pdf.setLineWidth(1)
        pdf.line(38, 696, 574, 696)
        pdf.setStrokeColor(GREEN)
        pdf.setLineWidth(2)
        pdf.line(38, 696, 145, 696)

        if first_page:
            pdf.setFillColor(GREEN_DARK)
            pdf.setFont("Helvetica-Bold", 7)
            pdf.drawString(38, 675, "SHIP TO")
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(38, 654, _fit_text(order.get("customer") or "Company name", "Helvetica-Bold", 16, 260))
            pdf.setFillColor(MUTED)
            pdf.setFont("Helvetica", 8.5)
            address_y = 637
            for line in _wrap(order.get("address") or "Ship To address", "Helvetica", 8.5, 250, 4):
                pdf.drawString(38, address_y, line)
                address_y -= 12

            facts = [
                ("INVOICE DATE", order.get("invoice_date") or "-"),
                ("SHIP DATE", order.get("ship_date") or "Pending"),
                ("DELIVERY DATE", order.get("delivery_date") or "Pending"),
                ("CARRIER", order.get("carrier") or "Pending"),
                ("TRACKING", order.get("tracking") or "Pending"),
            ]
            if is_zentite(order):
                facts.append(("DEVICE SN", order.get("device_serial") or "Pending"))
            pdf.setStrokeColor(LINE)
            pdf.setLineWidth(0.7)
            pdf.line(345, 674, 345, 590)
            fact_y = 674
            for label, value in facts:
                pdf.setFillColor(MUTED)
                pdf.setFont("Helvetica-Bold", 6.5)
                pdf.drawString(361, fact_y, label)
                pdf.setFillColor(GREEN_DARK if label == "DEVICE SN" else INK)
                pdf.setFont("Helvetica-Bold", 8)
                pdf.drawRightString(574, fact_y, _fit_text(value, "Helvetica-Bold", 8, 126))
                fact_y -= 14
            table_y = 578
        else:
            pdf.setFillColor(GREEN_DARK)
            pdf.setFont("Helvetica-Bold", 7)
            pdf.drawString(38, 675, f"SHIPMENT CONTENTS - CONTINUED ({page_index + 1}/{len(chunks)})")
            table_y = 653

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(38, table_y + 11, "SHIPMENT CONTENTS")
        pdf.setFillColor(INK)
        pdf.rect(38, table_y - 19, 536, 20, stroke=0, fill=1)
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 6.5)
        pdf.drawCentredString(53, table_y - 12, "#")
        pdf.drawString(69, table_y - 12, "ITEM")
        pdf.drawString(442, table_y - 12, "SERIAL / LOT")
        pdf.drawCentredString(556, table_y - 12, "QTY")
        row_y = table_y - 35
        global_start = page_index * page_size
        for index, item in enumerate(chunk, start=1):
            global_index = global_start + index
            serial = order.get("device_serial", "") if canonical_name(item.get("name", "")) == "unicorn-plus" else item.get("serial", "")
            pdf.setFillColor(MUTED)
            pdf.setFont("Helvetica", 6.5)
            pdf.drawCentredString(53, row_y, f"{global_index:02d}")
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 7.5)
            pdf.drawString(69, row_y, _fit_text(item.get("name", "Shipment item"), "Helvetica-Bold", 7.5, 350))
            pdf.setFillColor(GREEN_DARK if canonical_name(item.get("name", "")) == "unicorn-plus" else MUTED)
            pdf.setFont("Helvetica-Bold", 7)
            pdf.drawString(442, row_y, _fit_text(serial or "-", "Helvetica-Bold", 7, 82))
            pdf.setFillColor(INK)
            pdf.drawCentredString(556, row_y, str(int(item.get("quantity", 1))))
            pdf.setStrokeColor(LINE)
            pdf.setLineWidth(0.45)
            pdf.line(38, row_y - 6, 574, row_y - 6)
            row_y -= 16

        if last_page:
            panel_y = 92
            panel_h = 78
            pdf.setFillColor(colors.HexColor("#F8FAF8"))
            pdf.setStrokeColor(LINE)
            pdf.rect(38, panel_y, 312, panel_h, stroke=1, fill=1)
            pdf.setFillColor(GREEN_DARK)
            pdf.setFont("Helvetica-Bold", 7)
            pdf.drawString(50, panel_y + 61, "DELIVERY NOTES")
            pdf.setFillColor(MUTED)
            pdf.setFont("Helvetica", 7)
            note = order.get("notes") or "Please inspect the shipment upon arrival and retain this packing list for your records."
            note_y = panel_y + 45
            for line in _wrap(note, "Helvetica", 7, 286, 3):
                pdf.drawString(50, note_y, line)
                note_y -= 10
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 6.5)
            pdf.drawString(50, panel_y + 10, DELIVERY_EMAIL)

            pdf.setFillColor(GREEN_SOFT)
            pdf.setStrokeColor(colors.HexColor("#CBE5CE"))
            pdf.rect(360, panel_y, 214, panel_h, stroke=1, fill=1)
            qr_image = qrcode.make(INSTALLATION_URL)
            qr_buffer = BytesIO()
            qr_image.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)
            pdf.drawImage(ImageReader(qr_buffer), 371, panel_y + 10, width=58, height=58, mask="auto")
            pdf.setFillColor(GREEN_DARK)
            pdf.setFont("Helvetica-Bold", 6.5)
            pdf.drawString(440, panel_y + 55, "ZENTITE INSTALLATION")
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(440, panel_y + 36, "Scan to watch")
            pdf.setFillColor(MUTED)
            pdf.setFont("Helvetica", 6.5)
            pdf.drawString(440, panel_y + 23, "Setup & installation video")

        pdf.setStrokeColor(LINE)
        pdf.setLineWidth(0.6)
        pdf.line(38, 70, 574, 70)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 6.5)
        pdf.drawString(38, 54, "BOSTON AESTHETICS INC.")
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 6.2)
        pdf.drawString(38, 43, "1 Peters Canyon Rd, Suite 100 - Irvine, CA 92606")
        pdf.setFillColor(GREEN_DARK)
        pdf.setFont("Helvetica-Bold", 6.5)
        pdf.drawRightString(574, 49, "bostonaesthetics.com")
        pdf.showPage()

    pdf.save()
    return output.getvalue()

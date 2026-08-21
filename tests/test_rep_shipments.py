from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from packing_list import (
    build_packing_list_pdf,
    client_delivery_notes,
    demo_order,
    demo_rep_shipment,
    email_html,
    email_subject,
    email_text,
    load_demo_inventory,
    load_rep_directory,
    tracking_url,
)


ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "ba-logo.webp"


def pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_garrett_demo_is_source_faithful():
    shipment = demo_rep_shipment()
    assert shipment["customer"] == "Garrett Rolfe"
    assert shipment["recipient_title"] == "Territory Sales Manager"
    assert shipment["address"] == "729 Old Metairie Drive\nMetairie, LA 70001-6304"
    assert shipment["phone"] == "(318) 676-9697"
    assert shipment["email"] == "garrett.rolfe@bostonaesthestics.com"
    assert shipment["email_verified"] is False
    assert sum(item["quantity"] for item in shipment["items"]) == 45
    assert any("0268-26 SDF" in item["serial"] for item in shipment["items"])
    assert sum("NON-STERILE" in item["name"] for item in shipment["items"]) == 3


def test_rep_and_inventory_imports_preserve_values():
    reps = load_rep_directory(
        b"Sales Rep,Job Title,Shipping Address,City,State,Zip,Phone,Email\n"
        b"Garrett Rolfe,Territory Sales Manager,729 Old Metairie,Metairie,LA,70001,(318) 676-9697,garrett.rolfe@bostonaesthestics.com\n",
        "reps.csv",
    )
    assert reps.iloc[0]["email"] == "garrett.rolfe@bostonaesthestics.com"
    assert bool(reps.iloc[0]["verified"]) is False
    items = load_demo_inventory(
        b"Description,PICKED,Lot Number List for packing list\n"
        b"MicroRF 9N,12,286-25 SD; 0268-26 SD; 0268-26 SDF\n",
        "inventory.csv",
    )
    assert items[0]["quantity"] == 12
    assert items[0]["serial"] == "286-25 SD; 0268-26 SD; 0268-26 SDF"


def test_rep_pdf_and_tracking_email():
    shipment = demo_rep_shipment()
    shipment.update(
        {
            "shipment_reference": "DEMO-2026-001",
            "carrier": "UPS",
            "tracking": "1Z9999999999999999",
            "ship_date": "08/21/2026",
            "delivery_date": "08/24/2026",
        }
    )
    pdf = build_packing_list_pdf(shipment, LOGO)
    reader = PdfReader(BytesIO(pdf))
    text = pdf_text(pdf)
    assert len(reader.pages) == 1
    assert "DEMO SHIPMENT" in text
    assert "Garrett Rolfe" in text
    assert "0268-26 SDF" in text
    assert "NON-STERILE" in text
    assert "ZENTITE INSTALLATION" not in text
    assert "Shelley" not in text
    assert "signature" not in text.lower()

    assert email_subject(shipment) == "Your Boston Aesthetics demo shipment has shipped"
    plain = email_text(shipment)
    branded = email_html(shipment, LOGO)
    assert "Hi Garrett," in plain
    assert "18" in plain and "MicroRF 25N" in plain
    assert "ZenTite installation video" not in plain
    assert "demo shipment has shipped" in branded


def test_customer_workflow_regressions_remain_intact():
    order = demo_order()
    order["tracking"] = "105193767"
    order["carrier"] = "Aeronet"
    assert tracking_url(order).endswith("housebill=105193767")
    assert "ZenTite installation video" in email_text(order)
    assert "ZenTite installation" in email_html(order, LOGO)
    client_note = client_delivery_notes(
        "MUST CALL POC TO SCHEDULE DELIVERY - DELIVERY HOURS 10-3PM WILL REQUIRE PICS OF FREIGHT AT DELIVERY - LIFTGATE/INSIDE/UNPACK AND REMOVE DEBRIS"
    )
    assert "10:00 AM and 3:00 PM" in client_note
    assert "debris removal" in client_note


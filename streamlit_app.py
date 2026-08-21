from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from packing_list import (
    blank_order,
    blank_rep_shipment,
    build_packing_list_pdf,
    demo_rep_directory,
    demo_rep_shipment,
    demo_order,
    email_html,
    email_subject,
    email_text,
    enrich_zentite_bundle,
    is_zentite,
    is_rep_shipment,
    load_demo_inventory,
    load_rep_directory,
    parse_qbo_pdf,
    sync_device_serial,
)


ROOT = Path(__file__).resolve().parent
LOGO_PATH = ROOT / "assets" / "ba-logo.webp"
if not LOGO_PATH.exists():
    LOGO_PATH = ROOT / "ba-logo.webp"

st.set_page_config(
    page_title="BA Packing List Studio",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root { --ba-green:#39b54a; --ba-dark:#171a18; --ba-soft:#eef9ef; }
      .stApp { background:#f4f6f3; color:var(--ba-dark); }
      [data-testid="stSidebar"] { background:#111311; }
      [data-testid="stSidebar"] * { color:#f6f8f6; }
      [data-testid="stSidebar"] .stButton button { border:1px solid #3f4940; background:#1d211e; color:#fff; }
      [data-testid="stSidebar"] .stButton button:hover { border-color:var(--ba-green); color:var(--ba-green); }
      .block-container { max-width:1380px; padding-top:1.4rem; padding-bottom:4rem; }
      .ba-header { display:flex; align-items:center; justify-content:space-between; gap:24px; padding:16px 20px; border:1px solid #dde4dd; border-radius:14px; background:#fff; }
      .ba-header img { width:210px; height:auto; }
      .ba-header-copy { text-align:right; }
      .ba-header-copy span { color:#258d36; font-size:11px; font-weight:800; letter-spacing:.18em; }
      .ba-header-copy h1 { margin:3px 0 0; color:#171a18; font-size:26px; letter-spacing:-.03em; }
      .workflow-note { margin:14px 0 4px; padding:11px 14px; border-left:4px solid var(--ba-green); border-radius:0 8px 8px 0; background:var(--ba-soft); color:#4e5b50; font-size:13px; }
      .status-ok, .status-warn { padding:10px 12px; border-radius:9px; font-size:13px; font-weight:650; }
      .status-ok { background:#e4f6e6; color:#258d36; }
      .status-warn { background:#fff1d9; color:#8e5f16; }
      .preview-card { padding:24px; border:1px solid #dce3dc; border-top:5px solid #39b54a; border-radius:12px; background:#fff; box-shadow:0 12px 34px rgba(17,28,19,.07); }
      .preview-title { display:flex; justify-content:space-between; gap:20px; border-bottom:1px solid #dce3dc; padding-bottom:16px; }
      .preview-title h2 { margin:0; font-size:24px; font-weight:500; letter-spacing:.08em; }
      .preview-title b { color:#258d36; font-size:11px; }
      .preview-grid { display:grid; grid-template-columns:1fr 1fr; gap:28px; margin:20px 0; }
      .preview-grid small { display:block; margin-bottom:7px; color:#258d36; font-weight:800; letter-spacing:.12em; }
      .preview-grid p { margin:3px 0; color:#566158; white-space:pre-line; }
      div[data-testid="stDownloadButton"] button, div[data-testid="stButton"] button[kind="primary"] { background:#171a18; color:#fff; border-color:#171a18; }
      div[data-testid="stDownloadButton"] button:hover, div[data-testid="stButton"] button[kind="primary"]:hover { background:#258d36; border-color:#258d36; color:#fff; }
      .footer-note { margin-top:20px; color:#737d74; font-size:12px; }
      @media (max-width: 720px) {
        .ba-header { align-items:flex-start; flex-direction:column; }
        .ba-header-copy { text-align:left; }
        .preview-grid { grid-template-columns:1fr; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def reset_order(order: dict, filename: str = "") -> None:
    st.session_state.order = order
    st.session_state.filename = filename
    st.session_state.revision = st.session_state.get("revision", 0) + 1
    active = st.session_state.get("active_workflow")
    if active and "saved_orders" in st.session_state:
        st.session_state.saved_orders[active] = deepcopy(order)


def apply_rep_to_order(order: dict, rep: dict) -> dict:
    result = deepcopy(order)
    city_line = ", ".join(
        part
        for part in (
            str(rep.get("city", "")).strip(),
            " ".join(
                part
                for part in (str(rep.get("state", "")).strip(), str(rep.get("postal_code", "")).strip())
                if part
            ),
        )
        if part
    )
    result.update(
        {
            "shipment_type": "rep_demo",
            "customer": str(rep.get("name", "")).strip(),
            "recipient_title": str(rep.get("title", "")).strip(),
            "address": "\n".join(
                str(value).strip()
                for value in (rep.get("address1", ""), rep.get("address2", ""), city_line)
                if str(value or "").strip()
            ),
            "phone": str(rep.get("phone", "")).strip(),
            "email": str(rep.get("email", "")).strip(),
            "email_verified": bool(rep.get("email_verified", False)),
            "reviewed": False,
        }
    )
    return result


WORKFLOWS = ["Customer order", "Demo / rep shipment"]
if "active_workflow" not in st.session_state:
    st.session_state.active_workflow = WORKFLOWS[0]
if "saved_orders" not in st.session_state:
    st.session_state.saved_orders = {
        WORKFLOWS[0]: blank_order(),
        WORKFLOWS[1]: demo_rep_shipment(),
    }
if "order" not in st.session_state:
    reset_order(deepcopy(st.session_state.saved_orders[st.session_state.active_workflow]))
if "upload_hash" not in st.session_state:
    st.session_state.upload_hash = ""
if "rep_upload_hash" not in st.session_state:
    st.session_state.rep_upload_hash = ""
if "inventory_upload_hash" not in st.session_state:
    st.session_state.inventory_upload_hash = ""
if "client_email" not in st.session_state:
    st.session_state.client_email = ""
if "rep_directory" not in st.session_state:
    st.session_state.rep_directory = demo_rep_directory()
if "selected_rep" not in st.session_state:
    st.session_state.selected_rep = "Garrett Rolfe"


with st.sidebar:
    st.image(str(LOGO_PATH), width="stretch")
    st.markdown("### Shipment workflow")
    selected_workflow = st.radio("Shipment type", WORKFLOWS, index=WORKFLOWS.index(st.session_state.active_workflow))
    if selected_workflow != st.session_state.active_workflow:
        st.session_state.saved_orders[st.session_state.active_workflow] = deepcopy(st.session_state.order)
        st.session_state.active_workflow = selected_workflow
        st.session_state.order = deepcopy(st.session_state.saved_orders[selected_workflow])
        st.session_state.filename = ""
        st.session_state.revision += 1
        st.session_state.upload_hash = ""
        st.rerun()
    rep_mode = selected_workflow == WORKFLOWS[1]
    st.caption(
        "Rep directory → demo inventory → packing list + tracking email"
        if rep_mode
        else "QBO PDF → branded packing list → client tracking email"
    )
    st.divider()
    if st.button("Load Garrett demo shipment" if rep_mode else "Load example order", width="stretch"):
        reset_order(demo_rep_shipment() if rep_mode else demo_order(), "Garrett demo shipment" if rep_mode else "Example ZenTite order")
        st.session_state.upload_hash = ""
        st.rerun()
    if st.button("Start a blank demo shipment" if rep_mode else "Start a blank order", width="stretch"):
        reset_order(blank_rep_shipment() if rep_mode else blank_order())
        st.session_state.upload_hash = ""
        st.rerun()
    st.divider()
    st.caption("Uploaded PDFs are processed for the current session and are not saved by this app.")


st.markdown(
    f"""
    <div class="ba-header">
      <img src="data:image/webp;base64,{__import__('base64').b64encode(LOGO_PATH.read_bytes()).decode()}" alt="Boston Aesthetics">
      <div class="ba-header-copy"><span>OPERATIONS</span><h1>Packing List Studio</h1></div>
    </div>
    <div class="workflow-note">{'Select a verified rep, import or enter demo inventory and lots, then review the packing list and tracking email.' if rep_mode else 'The app reads the Ship To box, the values beside INVOICE and DATE, and the QBO line-item table by position. ZenTite systems are then enriched with the standard packing contents.'}</div>
    """,
    unsafe_allow_html=True,
)

tab_import, tab_document, tab_email = st.tabs(
    ["1 · Rep & inventory" if rep_mode else "1 · Import & review", "2 · Packing list", "3 · Tracking email" if rep_mode else "3 · Client email"]
)


with tab_import:
    order = st.session_state.order
    revision = st.session_state.revision
    if not rep_mode:
        st.subheader("Import the QuickBooks packing slip")
        upload = st.file_uploader("Drop the QBO packing-slip PDF here", type=["pdf"], help="Only the current session uses this file.")
        if upload is not None:
            uploaded_bytes = upload.getvalue()
            digest = hashlib.sha256(uploaded_bytes).hexdigest()
            if digest != st.session_state.upload_hash:
                try:
                    parsed = parse_qbo_pdf(uploaded_bytes)
                    reset_order(parsed, upload.name)
                    st.session_state.upload_hash = digest
                    st.success("Import complete. Review the extracted fields before downloading or emailing.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"This PDF could not be read automatically. You can still enter the order manually. ({exc})")
        if st.session_state.get("filename"):
            st.caption(f"Current source: {st.session_state.filename}")

        st.markdown("#### Confirm the shipment")
        column_a, column_b = st.columns(2)
        with column_a:
            order["customer"] = st.text_input("Ship To company", value=order.get("customer", ""), key=f"customer_{revision}")
            order["address"] = st.text_area("Ship To address", value=order.get("address", ""), height=110, key=f"address_{revision}")
            order["invoice_number"] = st.text_input("Invoice number", value=order.get("invoice_number", ""), key=f"invoice_{revision}")
            order["invoice_date"] = st.text_input("Invoice date", value=order.get("invoice_date", ""), key=f"invoice_date_{revision}")
        with column_b:
            order["ship_date"] = st.text_input("Ship date", value=order.get("ship_date", ""), key=f"ship_date_{revision}")
            order["delivery_date"] = st.text_input(
                "Delivery date",
                value=order.get("delivery_date", ""),
                key=f"delivery_date_{revision}",
                help="Optional expected delivery date supplied by the carrier.",
            )
            order["carrier"] = st.text_input("Carrier", value=order.get("carrier", ""), key=f"carrier_{revision}")
            order["tracking"] = st.text_input("Tracking number", value=order.get("tracking", ""), key=f"tracking_{revision}")
            order["device_serial"] = st.text_input(
                "ZenTite / Unicorn+ device SN",
                value=order.get("device_serial", ""),
                key=f"serial_{revision}",
                help="The Unicorn+ serial is the serial for the complete ZenTite device.",
            )
            order["notes"] = st.text_area("Delivery notes", value=order.get("notes", ""), height=80, key=f"notes_{revision}")

        st.markdown("#### Confirm the shipment contents")
        info_col, action_col = st.columns([4, 1])
        with info_col:
            st.caption("ZenTite bundle contents are added automatically. Treatment tips remain separate QBO line items.")
        with action_col:
            if st.button("Restore ZenTite bundle", width="stretch"):
                reset_order(enrich_zentite_bundle(order, force=True), st.session_state.get("filename", ""))
                st.rerun()
    else:
        st.subheader("Select the rep and prepare the demo inventory")
        rep_upload = st.file_uploader(
            "Import rep contract-info workbook or verified directory",
            type=["xlsx", "xlsm", "csv"],
            help="Imported records stay in the current session. Verify addresses and emails before use.",
        )
        if rep_upload is not None:
            rep_bytes = rep_upload.getvalue()
            rep_digest = hashlib.sha256(rep_bytes).hexdigest()
            if rep_digest != st.session_state.rep_upload_hash:
                try:
                    st.session_state.rep_directory = load_rep_directory(rep_bytes, rep_upload.name)
                    st.session_state.rep_upload_hash = rep_digest
                    st.success(f"Imported {len(st.session_state.rep_directory)} rep record(s). Review the verification flags below.")
                except Exception as exc:
                    st.error(f"The rep directory could not be imported. ({exc})")

        with st.expander("Review rep directory", expanded=False):
            st.caption("Contract information is source material. Mark a record verified only after checking the shipping address and contact details.")
            st.session_state.rep_directory = st.data_editor(
                st.session_state.rep_directory,
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                key="rep_directory_editor",
                column_config={
                    "verified": st.column_config.CheckboxColumn("Address/contact verified"),
                    "email_verified": st.column_config.CheckboxColumn("Email verified"),
                    "active": st.column_config.CheckboxColumn("Active"),
                },
            )

        directory = st.session_state.rep_directory
        active_mask = directory["active"].map(lambda value: str(value).lower() in {"true", "1", "yes"}) if "active" in directory else pd.Series(True, index=directory.index)
        active_directory = directory[active_mask]
        if active_directory.empty:
            st.error("No active rep records are available. Add or activate one in the directory editor.")
            st.stop()
        rep_names = active_directory["name"].astype(str).tolist()
        selected_rep = st.selectbox(
            "Sales rep",
            rep_names,
            index=rep_names.index(st.session_state.selected_rep) if st.session_state.selected_rep in rep_names else 0,
        )
        selected_record = active_directory[active_directory["name"].astype(str) == selected_rep].iloc[0].to_dict()
        if selected_rep != st.session_state.selected_rep or not order.get("customer"):
            st.session_state.selected_rep = selected_rep
            reset_order(apply_rep_to_order(order, selected_record), f"Rep directory: {selected_rep}")
            st.rerun()
        if not bool(selected_record.get("verified", False)):
            st.warning("This rep record is not marked verified. Confirm the address and contact information before generating outputs.")
        if not bool(selected_record.get("email_verified", False)):
            st.warning("The rep email is not marked verified. The source value is preserved; confirm it before sending the tracking email.")
        if selected_record.get("source_note"):
            st.caption(str(selected_record["source_note"]))

        st.markdown("#### Confirm the recipient and shipping details")
        column_a, column_b = st.columns(2)
        with column_a:
            order["customer"] = st.text_input("Sales rep", value=order.get("customer", ""), key=f"customer_{revision}")
            order["recipient_title"] = st.text_input("Title", value=order.get("recipient_title", ""), key=f"title_{revision}")
            order["address"] = st.text_area("Ship To address", value=order.get("address", ""), height=92, key=f"address_{revision}")
            order["phone"] = st.text_input("Phone", value=order.get("phone", ""), key=f"phone_{revision}")
            order["email"] = st.text_input("Email", value=order.get("email", ""), key=f"email_{revision}")
            order["email_verified"] = st.checkbox(
                "I verified this email before sending",
                value=bool(order.get("email_verified", False)),
                key=f"email_verified_{revision}",
            )
        with column_b:
            order["shipment_reference"] = st.text_input("Shipment reference", value=order.get("shipment_reference", ""), key=f"reference_{revision}")
            order["ship_date"] = st.text_input("Ship date", value=order.get("ship_date", ""), key=f"ship_date_{revision}")
            order["delivery_date"] = st.text_input("Estimated delivery", value=order.get("delivery_date", ""), key=f"delivery_date_{revision}")
            order["carrier"] = st.text_input("Carrier", value=order.get("carrier", ""), key=f"carrier_{revision}")
            order["tracking"] = st.text_input("Tracking number", value=order.get("tracking", ""), key=f"tracking_{revision}")
            order["notes"] = st.text_area("Delivery notes", value=order.get("notes", ""), height=80, key=f"notes_{revision}")

        st.markdown("#### Confirm the demo inventory")
        inventory_upload = st.file_uploader(
            "Import inventory picking export",
            type=["csv", "xlsx", "xlsm"],
            help="The PICKED quantity and Lot Number List for packing list columns are recognized automatically.",
        )
        if inventory_upload is not None:
            inventory_bytes = inventory_upload.getvalue()
            inventory_digest = hashlib.sha256(inventory_bytes).hexdigest()
            if inventory_digest != st.session_state.inventory_upload_hash:
                try:
                    order["items"] = load_demo_inventory(inventory_bytes, inventory_upload.name)
                    order["reviewed"] = False
                    st.session_state.inventory_upload_hash = inventory_digest
                    reset_order(order, inventory_upload.name)
                    st.success("Inventory imported. Quantities and lot values were preserved from the source.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"The inventory export could not be imported. ({exc})")
        st.caption("Add rows manually or edit the imported quantities and lot values. NON-STERILE rows are highlighted in the PDF.")

    item_columns = ["name", "serial", "quantity", "source", "description"]
    items_df = pd.DataFrame(order.get("items", []), columns=item_columns)
    edited_df = st.data_editor(
        items_df,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"items_{revision}",
        column_config={
            "name": st.column_config.TextColumn("Item", required=True, width="large"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "serial": st.column_config.TextColumn("Serial / lot", help="SN and Lot values from the QBO Description are copied here automatically."),
            "quantity": st.column_config.NumberColumn("Qty", min_value=1, step=1, required=True, width="small"),
            "source": st.column_config.SelectboxColumn("Source", options=["QBO", "ZenTite bundle", "Demo inventory", "Manual"], width="small"),
        },
    )
    clean_items = []
    for record in edited_df.fillna("").to_dict("records"):
        if not str(record.get("name", "")).strip():
            continue
        record["quantity"] = max(1, int(record.get("quantity") or 1))
        clean_items.append(record)
    order["items"] = clean_items
    st.session_state.order = sync_device_serial(order)

    required = (
        [
            not order.get("customer") and "sales rep",
            not order.get("address") and "Ship To address",
            not order.get("items") and "demo inventory",
        ]
        if rep_mode
        else [
            not order.get("customer") and "Ship To company",
            not order.get("address") and "Ship To address",
            not order.get("invoice_number") and "invoice number",
            not order.get("invoice_date") and "invoice date",
            not order.get("items") and "shipment contents",
            is_zentite(order) and not order.get("device_serial") and "Unicorn+ device SN",
        ]
    )
    required = [field for field in required if field]
    if required:
        st.markdown(f'<div class="status-warn">Required before finalizing: {", ".join(required)}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-ok">Required packing-list fields are complete.</div>', unsafe_allow_html=True)
    if rep_mode:
        for warning in order.get("quality_warnings", []):
            st.warning(warning)
        logistics_missing = [label for key, label in (("ship_date", "ship date"), ("delivery_date", "ETA"), ("carrier", "carrier"), ("tracking", "tracking number")) if not order.get(key)]
        if logistics_missing:
            st.warning(f"Still missing for the tracking email: {', '.join(logistics_missing)}.")
        order["reviewed"] = st.checkbox(
            "I reviewed the rep address, inventory quantities, lot values, and shipping details.",
            value=bool(order.get("reviewed", False)),
            key=f"reviewed_{revision}",
        )
    st.session_state.order = sync_device_serial(order)
    st.session_state.saved_orders[st.session_state.active_workflow] = deepcopy(st.session_state.order)


with tab_document:
    order = sync_device_serial(st.session_state.order)
    st.subheader("Branded printable packing list")
    logistics_pending = [label for key, label in [("ship_date", "ship date"), ("carrier", "carrier"), ("tracking", "tracking")] if not order.get(key)]
    if logistics_pending:
        st.warning(f"The packing list can still be downloaded, but these fields are pending: {', '.join(logistics_pending)}.")
    st.markdown(
        f"""
        <div class="preview-card">
          <div class="preview-title"><div><b>BOSTON AESTHETICS</b><h2>PACKING LIST</h2></div><div><b>{'DEMO SHIPMENT' if rep_mode else 'INVOICE'}</b><br>{order.get('shipment_reference') or 'REP INVENTORY' if rep_mode else order.get('invoice_number') or 'PENDING'}</div></div>
          <div class="preview-grid">
            <div><small>SHIP TO</small><strong>{order.get('customer') or 'Recipient'}</strong><p>{(order.get('recipient_title') + chr(10)) if rep_mode and order.get('recipient_title') else ''}{order.get('address') or 'Ship To address'}{(chr(10) + order.get('phone', '') + chr(10) + order.get('email', '')) if rep_mode else ''}</p></div>
            <div><small>SHIPMENT</small>{f'<p><strong>Invoice date:</strong> {order.get("invoice_date") or "-"}</p>' if not rep_mode else ''}<p><strong>Ship date:</strong> {order.get('ship_date') or 'Pending'}</p><p><strong>Delivery date:</strong> {order.get('delivery_date') or 'Pending'}</p><p><strong>Carrier:</strong> {order.get('carrier') or 'Pending'}</p><p><strong>Tracking:</strong> {order.get('tracking') or 'Pending'}</p>{f'<p><strong>Device SN:</strong> {order.get("device_serial") or "Pending"}</p>' if is_zentite(order) else ''}</div>
          </div>
          <small>{len(order.get('items', []))} shipment line items{' · Includes ZenTite installation QR code' if is_zentite(order) else ''} · No customer signature required</small>
        </div>
        """,
        unsafe_allow_html=True,
    )
    pdf_bytes = build_packing_list_pdf(order, LOGO_PATH)
    output_reference = order.get("shipment_reference") or order.get("customer") if rep_mode else order.get("invoice_number")
    safe_invoice = "".join(character for character in (output_reference or "packing-list") if character.isalnum() or character in "-_")
    rep_document_blocked = rep_mode and (
        not order.get("customer") or not order.get("address") or not order.get("items") or not order.get("reviewed")
    )
    if rep_mode and not order.get("reviewed"):
        st.warning("Complete the review checkbox on the Rep & inventory tab before downloading the packing list.")
    st.download_button(
        "Download branded packing list PDF",
        data=pdf_bytes,
        file_name=f"BA-Packing-List-{safe_invoice}.pdf",
        mime="application/pdf",
        type="primary",
        width="stretch",
        disabled=rep_document_blocked,
    )


def email_component(markup: str, plain_text: str) -> str:
    markup_json = json.dumps(markup)
    text_json = json.dumps(plain_text)
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;">
      <div style="display:flex;gap:8px;margin:0 0 12px;">
        <button id="copy-html" style="padding:10px 14px;border:0;border-radius:7px;background:#258d36;color:white;font-weight:700;cursor:pointer;">Copy branded email</button>
        <button id="copy-text" style="padding:10px 14px;border:1px solid #cdd5cd;border-radius:7px;background:white;color:#171a18;font-weight:700;cursor:pointer;">Copy plain text</button>
        <span id="copy-status" style="align-self:center;color:#69716b;font-size:12px;"></span>
      </div>
      <div>{markup}</div>
    </div>
    <script>
      const branded = {markup_json};
      const plain = {text_json};
      const status = document.getElementById('copy-status');
      document.getElementById('copy-html').onclick = async () => {{
        try {{
          await navigator.clipboard.write([new ClipboardItem({{
            'text/html': new Blob([branded], {{type:'text/html'}}),
            'text/plain': new Blob([plain], {{type:'text/plain'}})
          }})]);
          status.textContent = 'Copied - paste into an HTML Outlook message.';
        }} catch (error) {{
          await navigator.clipboard.writeText(plain);
          status.textContent = 'Plain text copied as a browser fallback.';
        }}
      }};
      document.getElementById('copy-text').onclick = async () => {{
        await navigator.clipboard.writeText(plain);
        status.textContent = 'Plain text copied.';
      }};
    </script>
    """


with tab_email:
    order = sync_device_serial(st.session_state.order)
    st.subheader("Rep tracking email" if rep_mode else "Client tracking email")
    email_ready = bool(
        order.get("customer")
        and order.get("carrier")
        and order.get("tracking")
        and order.get("items")
        and (not rep_mode or order.get("reviewed"))
        and (not rep_mode or order.get("email_verified"))
    )
    default_email = order.get("email", "") if rep_mode else st.session_state.client_email
    st.session_state.client_email = st.text_input(
        "Rep email address" if rep_mode else "Client email address",
        value=default_email,
        placeholder="Verify before opening Outlook" if rep_mode else "Optional until you open Outlook",
        key=f"tracking_email_{revision}",
    )
    subject = email_subject(order)
    plain = email_text(order)
    branded = email_html(order, LOGO_PATH)
    st.text_input("Subject", value=subject, disabled=True)
    if not email_ready:
        st.warning(
            "Review the rep shipment, verify the email, and add the carrier, tracking number, and inventory before using the tracking email."
            if rep_mode
            else "Add the customer, carrier, tracking number, and shipment contents before sending the client email."
        )
    else:
        mailto = f"mailto:{quote(st.session_state.client_email)}?subject={quote(subject)}&body={quote(plain)}"
        st.markdown(f'<a href="{mailto}" style="display:inline-block;margin:0 0 12px;padding:10px 15px;border-radius:7px;background:#171a18;color:#fff;text-decoration:none;font-weight:700;">Open Outlook draft</a>', unsafe_allow_html=True)
        components.html(email_component(branded, plain), height=760, scrolling=True)
        st.download_button("Download HTML email", branded, file_name=f"BA-Tracking-Email-{order.get('invoice_number') or 'draft'}.html", mime="text/html")
    with st.expander("Plain-text fallback"):
        st.text_area("Copy this version if HTML paste is unavailable", value=f"Subject: {subject}\n\n{plain}", height=420)

st.markdown('<div class="footer-note">Boston Aesthetics Operations · Delivery questions: info@bostonaesthetics.com</div>', unsafe_allow_html=True)

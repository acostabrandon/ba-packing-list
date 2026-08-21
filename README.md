# Boston Aesthetics Packing List Studio

A Streamlit app with two BA Operations shipment workflows.

### Customer order

- A reviewed, enriched ZenTite shipment record
- A branded printable packing-list PDF
- A branded HTML or plain-text client tracking email

### Demo / rep shipment

- Select a sales rep from an imported contract-info workbook or verified directory
- Populate the rep's address, title, phone, and email
- Import the inventory picking CSV/XLSX or add items and lots manually
- Enter carrier, tracking, ship date, and estimated delivery
- Review the rep address, inventory quantities, lots, and shipping details
- Generate the existing branded packing-list format plus a rep tracking email

The included Garrett example preserves the source workbook's email spelling and marks it unverified. It also preserves `0268-26 SDF` exactly and warns the user to verify it rather than silently correcting the lot.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

In the sidebar, choose **Customer order** or **Demo / rep shipment**. Switching modes preserves the current in-session draft for each workflow.

## Import columns

Rep directories accept common names such as `Sales Rep`, `Job Title`, `Shipping Address`, `City`, `State`, `Zip`, `Phone`, and `Email`. Optional `Verified`, `Email Verified`, and `Active` columns control the review warnings.

Inventory imports recognize `Description`/`Item`, `PICKED`/`Quantity`, and `Lot Number List for packing list`/`Lot Numbers`. Lot identifiers are handled as text and are not auto-corrected.

Sample import files are in `sample_data/`.

## Tests

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```

## Deploy on Streamlit Community Cloud

1. Push this folder to a GitHub repository.
2. In Streamlit Community Cloud, select **Create app**.
3. Choose the repository and `streamlit_app.py` as the entrypoint.
4. Keep the app private and invite teammates by email from **Share** if shipment information should not be public.

No secrets are required. Uploaded PDFs are processed in the active Streamlit session and are not written to persistent storage by the app.

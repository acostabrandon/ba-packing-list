# Boston Aesthetics Packing List Studio

A Streamlit app for turning a QuickBooks Online packing-slip PDF into:

- A reviewed, enriched ZenTite shipment record
- A branded printable packing-list PDF
- A branded HTML or plain-text client tracking email

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy on Streamlit Community Cloud

1. Push this folder to a GitHub repository.
2. In Streamlit Community Cloud, select **Create app**.
3. Choose the repository and `streamlit_app.py` as the entrypoint.
4. Keep the app private and invite teammates by email from **Share** if shipment information should not be public.

No secrets are required. Uploaded PDFs are processed in the active Streamlit session and are not written to persistent storage by the app.

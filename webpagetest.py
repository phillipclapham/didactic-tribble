import streamlit as st
import pandas as pd
import requests
from urllib.parse import urlparse
import json
from datetime import datetime
import time
import io
import csv
import numpy as np

def validate_urls(urls):
    """Validate URLs before processing"""
    invalid_urls = []
    for url in urls:
        try:
            parsed = urlparse(url.strip())
            if not parsed.scheme and not parsed.netloc:
                # If no scheme and no netloc, the whole thing might be the netloc
                url = 'https://' + url
                parsed = urlparse(url)

            if not parsed.netloc:
                invalid_urls.append((url, "Missing domain name"))
            elif '.' not in parsed.netloc:
                invalid_urls.append((url, "Invalid domain format"))

        except Exception as e:
            invalid_urls.append((url, str(e)))
    return invalid_urls

def test_site_with_retry(method, site_url, api_key, max_retries=3, delay=5):
    """Test a site with retry logic"""
    for attempt in range(max_retries):
        try:
            # Parse and clean the URL
            parsed_url = urlparse(site_url)
            clean_url = (parsed_url.netloc + parsed_url.path).rstrip('/')

            api_request_url = f'https://www.webpagetest.org/runtest.php?&url=https%3A%2F%2F{clean_url}&f=json'

            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-WPT-API-KEY': api_key,
                'User-Agent': 'Python'
            }

            with st.status(f"Attempt {attempt + 1} for {site_url}"):
                st.write(f"API Request URL: {api_request_url}")

                response = requests.request(method, api_request_url, headers=headers)
                response.raise_for_status()

                st.write(f"Response status code: {response.status_code}")
                return response.json()

        except Exception as e:
            if attempt < max_retries - 1:
                st.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                st.warning(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                st.error(f"All attempts failed for {site_url}: {str(e)}")
                return None

def detect_delimiter(file):
    """Detect if file is CSV or TSV by checking first line"""
    first_line = file.readline().decode('utf-8')
    file.seek(0)  # Reset file pointer to beginning
    if '\t' in first_line:
        return '\t'
    return ','

# Set page config
st.set_page_config(page_title="Pressable Bulk Performance Testing Tool", layout="wide")

# Main app
st.title("Pressable Bulk Performance Testing Tool")

# Add instructions
st.markdown("""
### Instructions:
1. Enter your API Key
2. Upload a CSV or TSV file with URLs (First column should contain URLs)
3. Click 'Run Tests' to begin processing
""")

# API Key handling
api_key = st.text_input("Enter your API Key", type="password")

# File upload
uploaded_file = st.file_uploader("Upload your file", type=['csv', 'tsv'])

if uploaded_file and api_key:
    try:
        # Detect delimiter and read file accordingly
        delimiter = detect_delimiter(uploaded_file)
        df = pd.read_csv(uploaded_file, sep=delimiter)

        # Get the name of the first column (which should contain URLs)
        url_column = df.columns[0]

        # Show preview of input data
        st.subheader("Preview of input data:")
        st.dataframe(df.head())

        # Validate URLs before processing
        invalid_urls = validate_urls(df[url_column])
        if invalid_urls:
            st.warning("Some URLs may need attention:")
            st.dataframe(pd.DataFrame(invalid_urls, columns=['URL', 'Issue']))

            # Add option to proceed anyway
            if not st.checkbox("Proceed with testing despite URL warnings"):
                st.stop()

        if st.button("Run Tests"):
            progress_bar = st.progress(0)
            status_container = st.empty()

            # Add new columns
            df['Date'] = datetime.now().strftime('%d %b %Y')
            df['Results'] = ''

            # Process each URL
            for idx, row in df.iterrows():
                site_url = row[url_column].strip()
                status_container.text(f"Processing {site_url}... ({idx + 1}/{len(df)})")

                # Call API with retry logic
                result = test_site_with_retry('POST', site_url, api_key)

                if result and 'data' in result and 'jsonUrl' in result['data']:
                    df.at[idx, 'Results'] = result['data']['jsonUrl']
                else:
                    df.at[idx, 'Results'] = 'Error processing URL'

                progress_bar.progress((idx + 1) / len(df))

            status_container.text("Processing complete! Download your results below.")

            # Results Analysis
            st.subheader("Results Analysis")
            col1, col2 = st.columns(2)

            with col1:
                success_rate = (df['Results'] != 'Error processing URL').mean() * 100
                st.metric("Success Rate", f"{success_rate:.1f}%")

            with col2:
                failed_urls = df[df['Results'] == 'Error processing URL'][url_column]
                if not failed_urls.empty:
                    st.write("Failed URLs:")
                    st.dataframe(failed_urls)
                else:
                    st.success("No failed URLs!")

            # Export Options
            st.subheader("Export Options")
            export_format = st.radio(
                "Choose export format:",
                ["TSV (Google Sheets compatible)", "CSV", "Excel", "JSON"]
            )

            if export_format == "TSV (Google Sheets compatible)":
                output = io.StringIO()
                df.to_csv(output, sep='\t', index=False, quoting=csv.QUOTE_MINIMAL)
                file_extension = "tsv"
                mime_type = "text/tab-separated-values"
            elif export_format == "CSV":
                output = io.StringIO()
                df.to_csv(output, index=False)
                file_extension = "csv"
                mime_type = "text/csv"
            elif export_format == "Excel":
                output = io.BytesIO()
                df.to_excel(output, index=False)
                file_extension = "xlsx"
                mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            else:  # JSON
                output = io.StringIO()
                df.to_json(output, orient='records')
                file_extension = "json"
                mime_type = "application/json"

            st.download_button(
                label=f"Download Results ({export_format})",
                data=output.getvalue(),
                file_name=f"webpagetest-results.{file_extension}",
                mime=mime_type
            )

    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        st.error("Full error details:", exc_info=True)
else:
    st.info("Please provide both an API key and upload a file to continue.")

# Add footer with instructions
st.markdown("""
---
### File Format Requirements:
- File can be either CSV (comma-separated) or TSV (tab-separated)
- First column should contain URLs
- URLs should be properly formatted (e.g., example.com or www.example.com)
- Second column should be the agency name
- Output will be provided in your chosen format
""")
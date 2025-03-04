# File: routes/pdf_converter.py
import casparser
import os
from dotenv import load_dotenv

def convertpdf(pdf_file_path, password, userid):
    """
    Converts a CAS PDF to CSV data.

    Args:
        pdf_file_path (str): The path to the CAS PDF file.
        password (str): The password for the CAS PDF file.

    Returns:
        str: The CSV data as a string, or None if an error occurs.
    """
    try:
        csv_str = casparser.read_cas_pdf(pdf_file_path, password, output="csv")
        print(casparser.read_cas_pdf(pdf_file_path, password))
        return csv_str
    except Exception as e:
        print(f"Error converting PDF: {e}")  # Log the error for debugging
        return e



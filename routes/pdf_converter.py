# pdf_converter.py
import casparser
import os
from dotenv import load_dotenv

def clear_folder(userid):
    """
    Clears the contents of a folder.

    Args:
        folder (str): The path to the folder to clear.

    Returns:
        None
    """
    load_dotenv()
    pwd = os.getenv("STORAGE_DIR")
    if not pwd:
        raise ValueError("STORAGE_DIR is not set in the .env file.")
    folder = os.path.join(pwd,userid,'output')
    # print(f"Clearing folder: {folder}")
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")  # Log the error for debugging

def convertpdf(pdf_file_path, password, userid):
    """
    Converts a CAS PDF to CSV data.

    Args:
        pdf_file_path (str): The path to the CAS PDF file.
        password (str): The password for the CAS PDF file.

    Returns:
        str: The CSV data as a string, or None if an error occurs.
    """
    # print(f"Clearing folder {userid}")
    clear_folder(userid)
    try:
        csv_str = casparser.read_cas_pdf(pdf_file_path, password, output="csv")
        print(casparser.read_cas_pdf(pdf_file_path, password))
        return csv_str
    except Exception as e:
        print(f"Error converting PDF: {e}")  # Log the error for debugging
        return e





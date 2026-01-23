import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
import datetime
import json

# Extracted from your screenshot
SHEET_ID = "18Cs5gzcBCfG5tFETyOgNcqU4bi8W-8g44PvD3NYkMaI"

def get_google_sheet_client():
    """
    Connects to Google Sheets using st.secrets (cloud) or credentials.json (local).
    """
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        creds = None
        # 1. Try Streamlit Secrets (for Cloud Deployment)
        try:
            if "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        except Exception:
            # Secrets not found (normal for local dev), fallback to file
            pass

        # 2. Try Local File (for Local Development) if secrets didn't work
        if not creds:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
            
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        # Only show sensitive error info if we confirm it's safe or simplified
        print(f"Auth Error: {e}")
        return None

def get_sheet_by_id(client):
    """Helper to open the sheet by ID, which is more robust than name."""
    try:
        if not client: return None
        return client.open_by_key(SHEET_ID)
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None

def get_students_data(client):
    """
    Fetches student data. Returns a DataFrame.
    """
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            worksheet = sheet.worksheet("Students")
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Error reading 'Students' tab: {e}")
            return pd.DataFrame() 
    else:
        # Mock Data (only if client/sheet failed entirely)
        if not client:
             st.warning("Using Mock Data (Not connected)")
             return pd.DataFrame({
                "Student Name": ["Alice Johnson", "Bob Smith", "Charlie Brown", "Diana Prince"],
                "Payment Status": ["Paid", "Pending", "Overdue", "Paid"],
                "Academic Progress": [75, 40, 10, 95],
                "Attendance": ["90%", "60%", "20%", "100%"]
            })
        return pd.DataFrame()

def add_review(client, teacher_name, student_name, review_text):
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            worksheet = sheet.worksheet("Reviews")
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            worksheet.append_row([timestamp, teacher_name, student_name, review_text])
            return True
        except Exception as e:
            st.error(f"Error saving review: {e}")
            return False
    return True # Mock success if no client

def add_student(client, student_data):
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            worksheet = sheet.worksheet("Students")
            row = [
                student_data.get("Name"),
                "Pending",  # Payment Status Default
                "0",        # Academic Progress
                "0%",       # Attendance
                "",         # Last Class Date
                student_data.get("Email"),
                student_data.get("Phone"),
                student_data.get("Class Times"),
                student_data.get("Subjects")
            ]
            worksheet.append_row(row)
            return True
        except Exception as e:
            st.error(f"Error saving student: {e}")
            return False
    return True

def add_teacher(client, teacher_data):
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            # check if Teachers tab exists
            try:
                worksheet = sheet.worksheet("Teachers")
            except gspread.exceptions.WorksheetNotFound:
                 st.error("'Teachers' worksheet not found in the Google Sheet.")
                 return False

            row = [
                teacher_data.get("Name"),
                teacher_data.get("Email"),
                teacher_data.get("Phone"),
                teacher_data.get("Expertise"),
                teacher_data.get("Assigned Students")
            ]
            worksheet.append_row(row)
            return True
        except Exception as e:
             st.error(f"Error saving teacher: {e}")
             return False
    return True


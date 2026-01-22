import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
import datetime

def get_google_sheet_client(credentials_file="credentials.json"):
    """
    Connects to Google Sheets using a service account credentials file.
    Returns None if credentials file is not found (for mock mode).
    """
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        return None

def get_students_data(client):
    """
    Fetches student data. Returns a DataFrame.
    If client is None, returns mock data.
    """
    if client:
        try:
            sheet = client.open("PAS Tutors Database")
            worksheet = sheet.worksheet("Students")
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
        except Exception:
            st.error("Could not fetch data from Google Sheets. Check your sheet name and permissions.")
            return pd.DataFrame() # Return empty to avoid crashes
    else:
        # Mock Data
        return pd.DataFrame({
            "Student Name": ["Alice Johnson", "Bob Smith", "Charlie Brown", "Diana Prince"],
            "Payment Status": ["Paid", "Pending", "Overdue", "Paid"],
            "Academic Progress": [75, 40, 10, 95],
            "Attendance": ["90%", "60%", "20%", "100%"]
        })

def add_review(client, teacher_name, student_name, review_text):
    """
    Appends a review to the 'Reviews' worksheet.
    Returns True if successful, False otherwise.
    """
    if client:
        try:
            sheet = client.open("PAS Tutors Data")
            worksheet = sheet.worksheet("Reviews")
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            worksheet.append_row([timestamp, teacher_name, student_name, review_text])
            return True
        except Exception as e:
            st.error(f"Error saving review: {e}")
            return False
    else:
        # Mock success
        return True

def add_student(client, student_data):
    """
    Appends a new student to the 'Students' worksheet.
    student_data is a dict containing: Name, Email, Phone, Class Times, Subjects.
    Defaults added: Payment Status='Pending', Academic Progress='0'.
    """
    if client:
        try:
            sheet = client.open("PAS Tutors Database")
            worksheet = sheet.worksheet("Students")
            # Expected columns: Student Name, Payment Status, Academic Progress, Attendance, Last Class Date, Email, Phone, Class Times, Subjects
            # We will append in a generic way, but let's try to match the structure if we can. 
            # For now, let's just append the fields we have in a logical order, assuming the sheet will be set up to match or we just append rows.
            # Based on previous structure: Student Name, Payment Status, Academic Progress, Attendance, Last Class Date
            # New fields needed: Email, Phone, Class Times, Subjects.
            # Let's assume the user adds these columns to the sheet.
            
            row = [
                student_data.get("Name"),
                "Pending",  # Payment Status Default
                "0",        # Academic Progress Default (as string or int)
                "0%",       # Attendance Default (initial)
                "",         # Last Class Date (empty)
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
    else:
        # Mock Mode
        return True

def add_teacher(client, teacher_data):
    """
    Appends a new teacher to the 'Teachers' worksheet.
    teacher_data is a dict containing: Name, Email, Phone, Expertise, Assigned Students.
    """
    if client:
        try:
            sheet = client.open("PAS Tutors Database")
            # check if Teachers tab exists, if not maybe warn? But usually we assume it exists.
            try:
                worksheet = sheet.worksheet("Teachers")
            except gspread.exceptions.WorksheetNotFound:
                 st.error("Traceback: 'Teachers' worksheet not found. Please create it.")
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
    else:
        # Mock Mode
        return True

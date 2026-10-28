import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
import datetime
import json
import re
import functools
import os
import uuid
import urllib.parse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# Global Subject Options
STANDARD_SUBJECTS = [
    "Maths", "English", "Physics", "Chemistry", "Biology", "Science", 
    "History", "Geography", "Literacy", "Reading", "Comprehension", 
    "Creative writing", "Spelling", "Grammar", "Grammer", "Spelling and Grammar", 
    "Verbal reasoning", "Quantitative reasoning", "Phonics", "Phonix", 
    "Social Studies", "Computer Science", "Art", "Music", "Other"
]

# Extracted from your screenshot
SHEET_ID = "18Cs5gzcBCfG5tFETyOgNcqU4bi8W-8g44PvD3NYkMaI"

def clean_currency(val):
    """
    Parses currency string to float.
    Examples: "55,000", "NGN 55000", "$100.00", " 500 ", ""
    """
    if pd.isna(val): return 0.0
    s = str(val).strip()
    if not s: return 0.0
    
    # Remove NGN, $, commas, spaces
    s_clean = re.sub(r'[^\d.]', '', s)
    
    try:
        return float(s_clean)
    except ValueError:
        return 0.0

def clean_billing_data(df):
    """
    Normalizes billing dataframe.
    """
    if df.empty: return df
    
    # 1. Normalize Column Names (Strip whitespace)
    df.columns = [c.strip() for c in df.columns]
    
    # 2. Normalize 'Billing Type' (lowercase)
    if "Billing Type" in df.columns:
        df["Billing Type"] = df["Billing Type"].astype(str).str.lower().str.strip()
    
    # 3. Clean 'Rate' or 'Rate/Amount' (Currency)
    # Check for likely rate columns
    rate_col = None
    if "Rate" in df.columns: rate_col = "Rate"
    elif "Rate/Amount" in df.columns: rate_col = "Rate/Amount"
    
    if rate_col:
        # Create a new clean column 'Rate_Clean' but also update original? 
        # Update original to be numeric for app usage
        # But wait, app might expect to show string? 
        # Better to keep 'Rate' numeric for calculations.
        
        # Rename "Rate/Amount" to "Rate" for consistency if needed?
        if rate_col == "Rate/Amount":
            df.rename(columns={"Rate/Amount": "Rate"}, inplace=True)
            rate_col = "Rate"
            
        df[rate_col] = df[rate_col].apply(clean_currency)
        
    return df


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

# Cache the client connection to avoid re-auth on every run
# Resource caching is for connections/objects
get_google_sheet_client = st.cache_resource(get_google_sheet_client)

import time
from func_timeout import func_timeout, FunctionTimedOut

def retry_on_quota(func):
    """
    Decorator to retry API calls on Quota Exceeded (429) or temporary server errors (500, 502, 503, 504).
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        retries = 3
        delay = 2
        for i in range(retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                retryable = any(k in err_str for k in ["429", "500", "502", "503", "504", "quota", "unavailable", "temporarily", "connection error"])
                if retryable and i < retries - 1:
                    time.sleep(delay)
                    delay *= 2 # Exponential backoff
                    continue
                raise e
        return func(*args, **kwargs)
    return wrapper

@st.cache_resource(ttl=600)
def get_sheet_by_id(_client):
    """
    Helper to open the sheet by ID. 
    Cached to prevent repeatedly fetching spreadsheet metadata.
    """
    try:
        if not _client: return None
        return _client.open_by_key(SHEET_ID)
    except Exception as e:
        err_str = str(e).lower()
        if "429" in err_str or "quota" in err_str:
             st.error("⚠️ Google API Quota Exceeded. Please wait a moment and refresh.")
        else:
             st.error(f"Connection Error: {e}")
        return None

@st.cache_data(ttl=600) # Cache for 10 minutes
@retry_on_quota
def get_students_data(_client):
    """
    Fetches student data. Returns a DataFrame.
    Prefix _client to prevent hashing the client object which might fail or be slow.
    """
    sheet = get_sheet_by_id(_client)
    if sheet:
        try:
            worksheet = sheet.worksheet("Students")
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)
            if "Phone" in df.columns: df["Phone"] = df["Phone"].astype(str)
            if "Phone Number" in df.columns: df["Phone Number"] = df["Phone Number"].astype(str)
            return df
        except Exception as e:
            st.error(f"Error reading 'Students' tab: {e}")
            return pd.DataFrame() 
    else:
        # Mock Data (only if client/sheet failed entirely)
        if not _client:
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
            # Clear cache because data changed
            get_students_data.clear() # Indirectly might affect if we use it? No, but Reviews changed.
            # We don't have a get_reviews_data function yet, but calculate_teacher_pay uses it.
            # So we should clear any cache that relies on reviews.
            # Since we don't cache calculate_teacher_pay directly (it takes args), we rely on it calling helpers.
            # But wait, calculate_teacher_pay calls get_billing_data which IS cached. 
            # And it calls get_sheet_by_id. 
            # It calls ws_reviews.get_all_values(). This is RAW gspread call. Not cached.
            # So calculate_teacher_pay is fine.
            return True
        except Exception as e:
            st.error(f"Error saving review: {e}")
            return False
    return True # Mock success if no client

@st.cache_data(ttl=600) # Increased TTL to 10 mins
@retry_on_quota
def get_billing_data(_client):
    """
    Fetches billing data. Returns a DataFrame.
    """
    sheet = get_sheet_by_id(_client)
    if sheet:
        try:
            worksheet = sheet.worksheet("Billing")
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)
            return clean_billing_data(df)
        except Exception as e:
            st.error(f"Error reading 'Billing' tab: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def add_student(client, student_data, billing_data=None):
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            # 1. Add to Students Tab
            ws_students = sheet.worksheet("Students")
            row_student = [
                student_data.get("Name"),
                student_data.get("Email"),
                student_data.get("Phone"),
                student_data.get("Class Times"),
                student_data.get("Subjects"),
                "Pending",  # Payment Status Default
                "0",        # Academic Progress
                "0%",       # Attendance
                ""          # Last Class Date
            ]
            ws_students.append_row(row_student)

            # 2. Add to Billing Tab (if billing data provided)
            if billing_data:
                try:
                    ws_billing = sheet.worksheet("Billing")
                except gspread.exceptions.WorksheetNotFound:
                     # Create if not exists (optional, but good practice)
                     ws_billing = sheet.add_worksheet(title="Billing", rows="100", cols="20")
                     ws_billing.append_row(["Student Name", "Billing Type", "Rate", "Currency", "Payment Terms", "Current Balance", "Last Bill Date"])

                row_billing = [
                    student_data.get("Name"),
                    billing_data.get("Billing Type"),
                    billing_data.get("Rate"),
                    billing_data.get("Currency"),
                    billing_data.get("Payment Terms"),
                    ""  # Current Balance (Starts empty, calculated dynamically)
                    ""  # Last Bill Date
                ]
                ws_billing.append_row(row_billing)
            
            get_students_data.clear()
            get_billing_data.clear()
            
            # Sync teacher assignments (add this student to their Assigned Students lists)
            if "Selected Teachers" in student_data:
                sync_student_to_teachers(client, student_data.get("Name"), student_data.get("Selected Teachers"))
            
            # Sync teacher schedule based on class times
            sync_teacher_schedule_from_student(client, student_data.get("Name"))
            
            return True
        except Exception as e:
            st.error(f"Error saving student: {e}")
            return False
    return True

def delete_student(client, student_name):
    """
    Completely removes a student from Students, Billing, and unassigns them from all teachers.
    """
    sheet = get_sheet_by_id(client)
    if not sheet: return False, "No Sheet"
    
    try:
        # First, unassign from all teachers before they are removed
        sync_student_to_teachers(client, student_name, [])
        sync_teacher_schedule_from_student(client, student_name)
        
        # Remove from Students tab
        ws_students = sheet.worksheet("Students")
        s_cell = ws_students.find(student_name)
        if s_cell:
            ws_students.delete_rows(s_cell.row)
            
        # Try to remove from Billing tab
        try:
            ws_billing = sheet.worksheet("Billing")
            b_cell = ws_billing.find(student_name)
            if b_cell:
                ws_billing.delete_rows(b_cell.row)
        except:
            pass # Fail silently if billing doesn't have them
            
        get_students_data.clear()
        get_billing_data.clear()
        return True, "Student deleted successfully!"
    except Exception as e:
        return False, str(e)

def calculate_billing(client):
    """
    Billing Logic Flow:
    - Monthly Fixed: Trigger charge on 1st of month.
    - Per Hour/Class: Placeholder logic.
    """
    # This is a placeholder function that acts as the "Logic Flow" requested
    try:
        df_billing = get_billing_data(client)
        if df_billing.empty:
            return
        
        today = datetime.date.today()
        # Logic: If today is 1st of month, we 'trigger' charges for Monthly Fixed.
        # In a real app, we'd check if we already ran for this month to avoid duplicates.
        
        if today.day == 1:
            # Iterate and charge Monthly Fixed
            # This is where we would update the 'Current Balance' column in the sheet
            pass
            
    except Exception as e:
        print(f"Billing calculation error: {e}")

def update_billing_profile(client, student_name, billing_data, recalculate=False):
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            try:
                ws_billing = sheet.worksheet("Billing")
            except gspread.exceptions.WorksheetNotFound:
                ws_billing = sheet.add_worksheet(title="Billing", rows="100", cols="20")
                ws_billing.append_row(["Student Name", "Billing Type", "Rate", "Currency", "Payment Terms", "Current Balance", "Last Bill Date"])

            # Check if student exists
            cell = None
            try:
                cell = ws_billing.find(student_name)
            except gspread.exceptions.CellNotFound:
                pass
            
            # We NO LONGER calculate or write the balance to the sheet.
            # The 'Current Balance' column (index 6, Col F) will be left as is or blanked if we want.
            # Let's keep it as "" (empty string) to avoid confusion.
            balance_display = "" 

            if cell:
                # Update existing row
                row_num = cell.row
                # Update cols 2, 3, 4, 5, 6 (Billing Type, Rate, Currency, Terms, Balance)
                
                ws_billing.update(f"B{row_num}:F{row_num}", [[
                    billing_data.get("Billing Type"),
                     billing_data.get("Rate"),
                     billing_data.get("Currency"),
                     billing_data.get("Payment Terms"),
                     balance_display # Now empty
                ]])
            else:
                # Append new
                row_billing = [
                    student_name,
                    billing_data.get("Billing Type"),
                    billing_data.get("Rate"),
                    billing_data.get("Currency"),
                    billing_data.get("Payment Terms"),
                    balance_display, # Now empty
                    ""
                ]
                ws_billing.append_row(row_billing)
            get_billing_data.clear()
            return True, f"Billing updated for {student_name}."
        except Exception as e:
            st.error(f"Error updating billing: {e}")
            return False, str(e)
            
    return False, "No Sheet"

def get_all_student_balances(client):
    """
    Calculates current balance for ALL students dynamically.
    Returns DataFrame: [Student Name, Billing Type, Rate, Currency, Classes Count, Total Owed]
    """
    try:
        # 1. Get Billing Data
        df_billing = get_billing_data(client)
        if df_billing.empty:
            return pd.DataFrame()
            
        # 2. Get Reviews (for class counting)
        sheet = get_sheet_by_id(client)
        if not sheet: return pd.DataFrame()
        
        ws_reviews = sheet.worksheet("Reviews")
        # Review structure: Timestamp, Teacher Name, Student Name, Review
        # Student Name is Column C (index 3)
        # Fetch all student names from reviews to count
        all_reviews_students = ws_reviews.col_values(3) # List of student names
        
        results = []
        
        for _, row in df_billing.iterrows():
            s_name = row.get("Student Name", "").strip()
            if not s_name: continue
            
            b_type = row.get("Billing Type", "").lower()
            rate = row.get("Rate", 0.0)
            currency = row.get("Currency", "NGN")
            
            # Calculate Count
            count = all_reviews_students.count(s_name)
            
            total_owed = 0.0
            if b_type == "per class":
                total_owed = count * rate
            elif b_type == "per hour":
                # Assuming 1 hr = 1 class for now
                total_owed = count * rate
            elif b_type == "monthly fixed":
                # Logic for monthly is trickier without dates. 
                # For now, let's just show rate? Or 0 if handled elsewhere?
                # User asked for "Personal inputs doesn't display results"
                # Let's assume Monthly means they owe the Rate once per month?
                # For simple dashboard, let's just show the Rate as the "Monthly Dues"
                total_owed = rate 
            
            results.append({
                "Student Name": s_name,
                "Billing Type": b_type.title(),
                "Rate": rate,
                "Currency": currency,
                "Classes Count": count,
                "Total Owed": total_owed
            })
            
        return pd.DataFrame(results)

    except Exception as e:
        print(f"Error calculating all balances: {e}")
        return pd.DataFrame()

def calculate_historical_balance(client, student_name, rate, billing_type):
    """
    Counts classes from 'Reviews' tab and calculates total.
    """
    try:
        sheet = get_sheet_by_id(client)
        ws_reviews = sheet.worksheet("Reviews")
        # Review structure: Timestamp, Teacher Name, Student Name, Review
        # Student Name is Column C (index 3)
        
        # Get all values in Column C
        student_names = ws_reviews.col_values(3)
        count = student_names.count(student_name)
        
        if billing_type == "Per Class":
            return count * float(rate)
        elif billing_type == "Per Hour":
            # Assuming 1 hour per class for now
            return count * float(rate)
        
        return 0 # Fixed not calculated historically
        
    except Exception as e:
        print(f"Error calculating history: {e}")
        return 0

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

            # Based on user screenshot, order: 
            # Teacher Name (A), Email (B), Phone Number (C), Subject Expertise (D), Assigned Students (E), Class Schedule (F)
            row = [
                teacher_data.get("Name"),
                teacher_data.get("Email"),
                teacher_data.get("Phone"),
                teacher_data.get("Expertise"),
                teacher_data.get("Assigned Students"),
                teacher_data.get("Availability") # Mapped to Class Schedule
            ]
            worksheet.append_row(row)
            # Clear caches
            get_teacher_data.clear()
            return True
        except Exception as e:
             st.error(f"Error saving teacher: {e}")
             return False
    return True

@st.cache_data(ttl=600)
@retry_on_quota
def get_teacher_data(_client):
    sheet = get_sheet_by_id(_client)
    if sheet:
        try:
             worksheet = sheet.worksheet("Teachers")
             data = worksheet.get_all_records()
             df = pd.DataFrame(data)
             if "Phone" in df.columns: df["Phone"] = df["Phone"].astype(str)
             if "Phone Number" in df.columns: df["Phone Number"] = df["Phone Number"].astype(str)
             return df
        except Exception:
             return pd.DataFrame()
    return pd.DataFrame()

def calculate_teacher_pay(client, teacher_name, monthly_fee):
    """
    Calculates pay based on flat monthly fee. 
    Also calculates revenue generated by students taught by this teacher from Reviews.
    Returns: count (total classes), total_revenue, teacher_pay, df_breakdown
    """
    try:
        sheet = get_sheet_by_id(client)
        ws_reviews = sheet.worksheet("Reviews")
        # Review structure: Timestamp, Teacher Name, Student Name, Review
        # Index: 0, 1, 2, 3
        
        qt_reviews = ws_reviews.get_all_values()
        
        # 1. Filter reviews for this teacher
        teacher_reviews = [row for row in qt_reviews if len(row) > 2 and row[1] == teacher_name]
        count = len(teacher_reviews)
        
        if count == 0:
            return 0, 0.0, monthly_fee, pd.DataFrame()

        # 2. Get Billing Data for Lookups
        df_billing = get_billing_data(client)
        
        rate_map = {}
        if not df_billing.empty:
            for _, row in df_billing.iterrows():
                 s_name = str(row.get("Student Name", "")).strip()
                 rate_val = row.get("Rate", 0.0) 
                 if s_name:
                     rate_map[s_name] = rate_val

        # 3. Calculate Revenue and build breakdown
        breakdown = {}
        total_revenue = 0.0
        
        for review in teacher_reviews:
            if len(review) > 2:
                s_name = str(review[2]).strip()
                r = rate_map.get(s_name, 0.0)
                total_revenue += r
                
                if s_name not in breakdown:
                    breakdown[s_name] = {"Classes": 0, "Rate": r, "Revenue": 0.0}
                    
                breakdown[s_name]["Classes"] += 1
                breakdown[s_name]["Revenue"] += r
        
        df_breakdown = pd.DataFrame([
            {
                "Student": k, 
                "Classes Taught": v["Classes"], 
                "Student Rate (NGN)": v["Rate"], 
                "Revenue Generated (NGN)": v["Revenue"]
            }
            for k, v in breakdown.items()
        ])
        
        teacher_pay = monthly_fee
        return count, total_revenue, teacher_pay, df_breakdown

    except Exception as e:
        print(f"Error calc teacher pay: {e}")
        return 0, 0.0, 0.0, pd.DataFrame()

def estimate_monthly_classes(schedule_str):
    """
    Parses a schedule string like:
    "Tuesday (06:00 PM - 07:00 PM), Thursday (06:00 PM - 07:00 PM)"
    Returns estimated classes per month (Weekly Count * 4).
    """
    if not isinstance(schedule_str, str) or not schedule_str:
        return 0
    
    # Heuristic: The string is usually comma-separated for multiple slots
    # or just contains day names.
    # Simple approach: Split by ',' or count occurrences of '(' (which denotes a time slot)
    
    # If the format is consistent "Day (Time)", counting '(' is a robust proxy for number of slots.
    weekly_classes = schedule_str.count('(')
    
    if weekly_classes == 0:
        # Fallback: maybe just comma separated?
        if ',' in schedule_str:
             weekly_classes = len(schedule_str.split(','))
        elif len(schedule_str) > 5: # At least one entry
             weekly_classes = 1
             
    return weekly_classes * 4

def parse_schedule_string(schedule_str):
    """
    Parses "Monday (09:00 AM - 05:00 PM), Tuesday (...)"
    Returns dict: {"Monday": (start_time_obj, end_time_obj), ...}
    """
    if not isinstance(schedule_str, str) or not schedule_str:
        return {}
        
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    result = {}
    
    # Simple parsing strategy
    # 1. Split by ')' to get chunks? or just iterate days
    
    for day in days:
        if day in schedule_str:
            try:
                # Find content between Day ( and )
                # e.g. "Monday (09:00 AM - 05:00 PM)"
                start_idx = schedule_str.find(day + " (")
                if start_idx == -1: continue
                
                # Advance to time part
                content_start = start_idx + len(day) + 2 # skip " ("
                end_idx = schedule_str.find(")", content_start)
                
                time_part = schedule_str[content_start:end_idx] # "09:00 AM - 05:00 PM"
                
                t_strs = time_part.split(" - ")
                if len(t_strs) == 2:
                    t1 = datetime.datetime.strptime(t_strs[0].strip(), "%I:%M %p").time()
                    t2 = datetime.datetime.strptime(t_strs[1].strip(), "%I:%M %p").time()
                    result[day] = (t1, t2)
            except Exception:
                # If parsing fails, just mark day as present but default time?
                # Or skip. Let's return what we can.
                result[day] = (datetime.time(9, 0), datetime.time(17, 0)) # Default 9-5 if parse error
                
    return result

def get_student_teacher_map(client):
    """
    Returns a dict mapping Normalized Student Name -> List of Teachers.
    """
    df_teachers = get_teacher_data(client)
    student_teacher_map = {}
    
    if not df_teachers.empty and "Assigned Students" in df_teachers.columns:
        for _, t_row in df_teachers.iterrows():
            t_name = t_row.get("Teacher Name", "Unknown")
            assigned_raw = str(t_row.get("Assigned Students", ""))
            expertise_raw = str(t_row.get("Subject Expertise", ""))
            
            # Split by comma and normalize
            assigned_list = [a.strip().lower() for a in assigned_raw.split(',') if a.strip()]
            expertise_list = [e.strip().lower() for e in expertise_raw.split(',') if e.strip()]
            
            for s in assigned_list:
                if s not in student_teacher_map:
                    student_teacher_map[s] = []
                
                # Check for duplicates before appending to handle accidental dupes in Sheet
                if not any(t["name"] == t_name for t in student_teacher_map[s]):
                    student_teacher_map[s].append({
                        "name": t_name, 
                        "expertise": expertise_list
                    })
    return student_teacher_map


# --- NEW SCHEDULE LOGIC & VALIDATION ---

def parse_student_schedule(class_times_str):
    """
    Parses 'Subject (Day Time), Subject (Day Time)' string.
    Supports 'Subject (Day Start - End)' format.
    Returns list of dicts.
    """
    if not isinstance(class_times_str, str) or not class_times_str.strip():
        return []

    entries = []
    # Split by comma
    parts = [p.strip() for p in class_times_str.split(',')]
    
    day_map = {
        "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", 
        "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"
    }
    
    for part in parts:
        if not part: continue
        
        # Regex: Subject \((Day) (Start)( - End)?\) OR Subject \((Day) (Start)( - End)?\) \[Teacher\]
        # Group 1: Subject
        # Group 2: Day
        # Group 3: Start Time
        # Group 4: End Time (Optional)
        # Group 5: Teacher (Optional)
        pattern = r"^(.*?)\s*\(\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2}:\d{2}\s*[AP]M)(?:\s*-\s*(\d{1,2}:\d{2}\s*[AP]M))?\s*\)(?:\s*\[(.*?)\])?$"
        match = re.search(pattern, part, re.IGNORECASE)
        
        if match:
            subj = match.group(1).strip()
            day_short = match.group(2).title()
            start_str = match.group(3).upper()
            end_str = match.group(4).upper() if match.group(4) else None
            
            t_name_assigned = match.group(5).strip() if match.group(5) else None
            
            t_start_obj = None
            t_end_obj = None
            duration_str = "Unknown"
            
            try:
                t_start_obj = datetime.datetime.strptime(start_str, "%I:%M %p").time()
                if end_str:
                    t_end_obj = datetime.datetime.strptime(end_str, "%I:%M %p").time()
                    # Calculate duration
                    d1 = datetime.datetime.combine(datetime.date.today(), t_start_obj)
                    d2 = datetime.datetime.combine(datetime.date.today(), t_end_obj)
                    diff = d2 - d1
                    total_min = int(diff.total_seconds() / 60)
                    hours = total_min // 60
                    mins = total_min % 60
                    if hours > 0 and mins > 0:
                        duration_str = f"{hours}h {mins}m"
                    elif hours > 0:
                        duration_str = f"{hours}h"
                    else:
                        duration_str = f"{mins}m"
            except:
                pass

            entries.append({
                "Subject": subj,
                "Day": day_map.get(day_short, day_short),
                "Time": start_str,
                "EndTime": end_str,
                "TimeObj": t_start_obj,
                "Duration": duration_str,
                "AssignedTeacher": t_name_assigned,
                "Raw": part,
                "Valid": True
            })
        else:
            entries.append({
                "Raw": part,
                "Valid": False,
                "Error": "Format mismatch. Expected: 'Subject (Day Start - End)'"
            })
            
    return entries

def validate_data_integrity(client):
    """
    Checks for errors in Student 'Class Times' and returns a DataFrame of issues.
    """
    issues = []
    
    # 1. Check Students
    df_students = get_students_data(client)
    if not df_students.empty and "Class Times" in df_students.columns:
        for idx, row in df_students.iterrows():
            s_name = row.get("Student Name", f"Row {idx+2}")
            c_times = str(row.get("Class Times", ""))
            
            if not c_times.strip():
                continue # Empty is okay (maybe inactive)

            parsed = parse_student_schedule(c_times)
            for p in parsed:
                if not p["Valid"]:
                    issues.append({
                        "Type": "Student Schedule",
                        "Name": s_name,
                        "Issue": p["Error"],
                        "Raw Data": p["Raw"]
                    })
    
    # 2. Check Teachers (Schedule Parsing)
    df_teachers = get_teacher_data(client)
    if not df_teachers.empty:
        sched_col = "Class Schedule" if "Class Schedule" in df_teachers.columns else "Availability"
        if sched_col in df_teachers.columns:
            for idx, row in df_teachers.iterrows():
                t_name = row.get("Teacher Name", f"Row {idx+2}")
                sched = str(row.get(sched_col, ""))
                
                if sched.strip():
                    # The Teacher's Class Schedule is now synced from students' Class Times.
                    # It uses the format 'Subject (Day Start - End)'.
                    parsed = parse_student_schedule(sched)
                    
                    # If all parsed entries are invalid and there is some content, report an error
                    valid_entries = [p for p in parsed if p.get("Valid")]
                    
                    if not valid_entries and len(sched) > 10:
                         issues.append({
                            "Type": "Teacher Availability",
                            "Name": t_name,
                            "Issue": "Could not parse availability string.",
                            "Raw Data": sched
                        })

    return pd.DataFrame(issues)

    # 3. Check for Unassigned Students & Billing
    # Build Map
    student_teacher_map = get_student_teacher_map(client)
    
    if not df_students.empty and "Student Name" in df_students.columns:
         for idx, row in df_students.iterrows():
             s_name = row.get("Student Name", "").strip()
             if not s_name: continue
             
             # Check Assignment
             if s_name.lower() not in student_teacher_map:
                 issues.append({
                    "Type": "Unassigned Student",
                    "Name": s_name,
                    "Issue": "No teacher has this student listed in 'Assigned Students'.",
                    "Raw Data": "N/A"
                 })
             
             # Check Schedule Durations (Re-using parse loop from above would be efficient, but keeping logic clean)
             c_times = str(row.get("Class Times", ""))
             parsed = parse_student_schedule(c_times)
             for p in parsed:
                 if p["Valid"] and not p.get("EndTime"):
                     issues.append({
                        "Type": "Missing Duration",
                        "Name": s_name,
                        "Issue": f"Class '{p['Subject']}' has no end time.",
                        "Raw Data": p["Raw"]
                     })


    # 4. Check Billing Data
    df_billing = get_billing_data(client) 
    if not df_billing.empty:
         if "Rate" in df_billing.columns:
             for idx, r in df_billing.iterrows():
                 if r.get("Billing Type") in ["hourly", "monthly"] and r.get("Rate") == 0.0:
                      issues.append({
                        "Type": "Billing",
                        "Name": r.get("Student Name", f"Row {idx}"),
                        "Issue": "Rate is 0.0 (Possible format error)",
                        "Raw Data": "View Sheet"
                    })

    return pd.DataFrame(issues)

def generate_master_schedule(client, selected_day_full):
    """
    Generates a schedule based on Student Class Times.
    """
    agenda_items = []
    
    # 1. Get Students
    df_students = get_students_data(client)
    if df_students.empty or "Class Times" not in df_students.columns:
        return pd.DataFrame()

    # 2. Get Teachers (for matching) -> NOW USING HELPER
    student_teacher_map = get_student_teacher_map(client)

    # 3. Iterate Students and Build Schedule
    for _, s_row in df_students.iterrows():
        s_name = s_row.get("Student Name", "Unknown")
        c_times = str(s_row.get("Class Times", ""))
        
        parsed_classes = parse_student_schedule(c_times)
        
        for cls in parsed_classes:
            if not cls["Valid"]: continue
            
            if cls["Day"] == selected_day_full:
                if cls.get("AssignedTeacher"):
                    final_teacher = cls["AssignedTeacher"]
                else:
                    # MATCH TEACHER using Normalized Name and Subject Expertise (legacy fallback)
                    s_key = s_name.strip().lower()
                    subj_key = cls["Subject"].strip().lower()
                    potential_teachers_data = student_teacher_map.get(s_key, [])
                    
                    potential_teachers = []
                    for t in potential_teachers_data:
                        # Match if teacher has no expertise listed (fallback), or if their expertise includes this subject
                        if not t["expertise"] or subj_key in t["expertise"]:
                            potential_teachers.append(t["name"])
                    
                    final_teacher = "Unassigned"
                    if len(potential_teachers) == 1:
                        final_teacher = potential_teachers[0]
                    elif len(potential_teachers) > 1:
                        final_teacher = ", ".join(potential_teachers)
                
                agenda_items.append({
                    "Time": cls["Time"],
                    "EndTime": cls["EndTime"] if cls["EndTime"] else "-",
                    "Duration": cls["Duration"],
                    "TimeObj": cls["TimeObj"],
                    "Student": s_name,
                    "Subject": cls["Subject"],
                    "Teacher": final_teacher
                })

    # 4. Aggregate / Sort
    if not agenda_items:
        return pd.DataFrame()
        
    df = pd.DataFrame(agenda_items)
    
    # Sort by TimeObj
    df = df.sort_values(by="TimeObj")
    
    # Drop TimeObj before return
    df = df.drop(columns=["TimeObj"])
    
    # Reorder
    df = df[["Time", "EndTime", "Duration", "Teacher", "Subject", "Student"]]
    
    return df

@st.cache_data(ttl=300)
def get_teacher_master_schedule(_client, teacher_name, selected_day=None):
    """
    Pulls all recurring classes for a specific teacher directly from the master schedule
    (Student Class Times mapped to assigned teachers) and enriches with confirmed meeting links.
    """
    df_students = get_students_data(_client)
    if df_students.empty or "Class Times" not in df_students.columns:
        return pd.DataFrame()

    student_teacher_map = get_student_teacher_map(_client)
    clean_target_teacher = normalize_name(teacher_name)

    # 1. Map meeting links from Weekly_Plans tab
    df_wp = get_weekly_plans_data(_client)
    links_map = {}
    if not df_wp.empty and "Teacher Name" in df_wp.columns and "Student Name" in df_wp.columns and "Meeting Link" in df_wp.columns:
        for _, wp_row in df_wp.iterrows():
            t_clean = normalize_name(str(wp_row.get("Teacher Name", "")))
            s_clean = normalize_name(str(wp_row.get("Student Name", "")))
            m_link = str(wp_row.get("Meeting Link", "")).strip()
            if t_clean == clean_target_teacher and m_link:
                links_map[s_clean] = m_link

    # 2. Fallback meeting links from Sessions tab
    df_sess = get_sessions_data(_client)
    if not df_sess.empty and "Teacher Name" in df_sess.columns and "Student Name" in df_sess.columns and "Meeting Link" in df_sess.columns:
        for _, s_row in df_sess.iterrows():
            t_clean = normalize_name(str(s_row.get("Teacher Name", "")))
            s_clean = normalize_name(str(s_row.get("Student Name", "")))
            m_link = str(s_row.get("Meeting Link", "")).strip()
            if t_clean == clean_target_teacher and m_link and s_clean not in links_map:
                links_map[s_clean] = m_link

    day_order = {"Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4, "Friday": 5, "Saturday": 6, "Sunday": 7}
    classes = []

    for _, s_row in df_students.iterrows():
        s_name = s_row.get("Student Name", "Unknown")
        c_times = str(s_row.get("Class Times", ""))
        parsed_classes = parse_student_schedule(c_times)
        s_clean = normalize_name(s_name)

        for cls in parsed_classes:
            if not cls["Valid"]:
                continue

            if cls.get("AssignedTeacher"):
                final_teacher = cls["AssignedTeacher"]
            else:
                s_key = s_name.strip().lower()
                subj_key = cls["Subject"].strip().lower()
                potential_teachers_data = student_teacher_map.get(s_key, [])
                potential_teachers = []
                for t in potential_teachers_data:
                    if not t["expertise"] or subj_key in t["expertise"]:
                        potential_teachers.append(t["name"])
                final_teacher = "Unassigned"
                if len(potential_teachers) == 1:
                    final_teacher = potential_teachers[0]
                elif len(potential_teachers) > 1:
                    final_teacher = ", ".join(potential_teachers)

            if clean_target_teacher in normalize_name(final_teacher):
                cls_day = cls.get("Day", "")
                if selected_day and selected_day != "All Days" and cls_day.lower() != selected_day.lower():
                    continue

                classes.append({
                    "Day": cls_day,
                    "DayOrder": day_order.get(cls_day, 99),
                    "Time": cls["Time"],
                    "EndTime": cls["EndTime"] if cls["EndTime"] else "-",
                    "Duration": cls["Duration"],
                    "TimeObj": cls["TimeObj"],
                    "Student": s_name,
                    "Subject": cls["Subject"],
                    "MeetingLink": links_map.get(s_clean, "")
                })

    if not classes:
        return pd.DataFrame()

    df = pd.DataFrame(classes)
    df = df.sort_values(by=["DayOrder", "TimeObj"])
    df = df.drop(columns=["DayOrder", "TimeObj"])
    return df



# --- SESSION MANAGEMENT (PHASE 2) ---
import uuid
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Email Configuration
# Try to get from secrets, else use provided fallback
try:
    SENDER_EMAIL = st.secrets.get("EMAIL_USER", "Pinnacleassistance1@gmail.com")
    SENDER_PASSWORD = st.secrets.get("EMAIL_PASSWORD", "fjruhliqivocbnra") 
    BASE_APP_URL = st.secrets.get("APP_URL", "https://pas-dashboard-gcvkbpip4geh7cchnpgqya.streamlit.app")
except FileNotFoundError:
    # If no secrets.toml exists (local dev), use defaults
    SENDER_EMAIL = "Pinnacleassistance1@gmail.com"
    SENDER_PASSWORD = "fjruhliqivocbnra"
    BASE_APP_URL = "https://pas-dashboard-gcvkbpip4geh7cchnpgqya.streamlit.app" # Default to localhost if no secrets
except Exception:
    # Catch StreamlitSecretNotFoundError (which might be ImportError or other)
    SENDER_EMAIL = "Pinnacleassistance1@gmail.com"
    SENDER_PASSWORD = "fjruhliqivocbnra"
    BASE_APP_URL = "https://pas-dashboard-gcvkbpip4geh7cchnpgqya.streamlit.app"

def send_email_invite(teacher_email, student_email, subject, time_str, session_id, meeting_link):
    """
    Sends email with MAGIC LINKS to Teacher and Student.
    """
    try:
        # Create Messages
        # We send separate emails to personalize the link (Teacher vs Student Role)
        
        # 1. Send to Teacher
        msg_t = MIMEMultipart()
        msg_t['From'] = SENDER_EMAIL
        msg_t['To'] = teacher_email
        msg_t['Subject'] = f"Class Invitation: {subject} @ {time_str}"
        
        magic_link_t = f"{BASE_APP_URL}/?action=clock_in&session_id={session_id}&role=Teacher"
        
        body_t = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <h2 style="color: #4CAF50;">PAS Tutors Class Invitation</h2>
            <p><strong>Subject:</strong> {subject}</p>
            <p><strong>Time:</strong> {time_str}</p>
            <br>
            <a href="{magic_link_t}" style="background-color: #4CAF50; color: white; padding: 15px 32px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; border-radius: 5px;">
                JOIN CLASS (Teacher)
            </a>
            <p style="color: #666; font-size: 12px; margin-top: 20px;">Clicking this link will automatically clock you in and open the meeting.</p>
        </div>
        """
        msg_t.attach(MIMEText(body_t, 'html'))
        
        # 2. Send to Student
        msg_s = MIMEMultipart()
        msg_s['From'] = SENDER_EMAIL
        msg_s['To'] = student_email
        msg_s['Subject'] = f"Class Invitation: {subject} @ {time_str}"
        
        magic_link_s = f"{BASE_APP_URL}/?action=clock_in&session_id={session_id}&role=Student"
        
        body_s = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <h2 style="color: #2196F3;">PAS Tutors Class Invitation</h2>
            <p><strong>Subject:</strong> {subject}</p>
            <p><strong>Time:</strong> {time_str}</p>
            <br>
            <a href="{magic_link_s}" style="background-color: #2196F3; color: white; padding: 15px 32px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; border-radius: 5px;">
                JOIN CLASS (Student)
            </a>
            <p style="color: #666; font-size: 12px; margin-top: 20px;">Clicking this link will automatically clock you in and open the meeting.</p>
        </div>
        """
        msg_s.attach(MIMEText(body_s, 'html'))

        # Connect to Server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        server.sendmail(SENDER_EMAIL, teacher_email, msg_t.as_string())
        server.sendmail(SENDER_EMAIL, student_email, msg_s.as_string())
        
        server.quit()
        return True, "Invites Sent Successfully"
    except Exception as e:
        print(f"Email Error: {e}")
        return False, str(e)

def send_multi_email_invite(teacher_email, student_emails, subject, time_str, session_id, meeting_link):
    """
    Sends email with MAGIC LINKS to Teacher and Multiple Students.
    Teacher receives both Clock In and Clock Out (Survey) links.
    student_emails: list of tuples [(s_name, s_email), ...]
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    try:
        # Connect to Server once
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        # 1. Send to Teacher
        msg_t = MIMEMultipart()
        msg_t['From'] = SENDER_EMAIL
        msg_t['To'] = teacher_email
        msg_t['Subject'] = f"Class Invitation: {subject} @ {time_str}"
        
        magic_link_t = f"{BASE_APP_URL}/?action=clock_in&session_id={session_id}&role=Teacher"
        magic_link_end = f"{BASE_APP_URL}/?action=clock_out&session_id={session_id}&role=Teacher"
        
        body_t = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <h2 style="color: #4CAF50;">PAS Tutors Class Invitation</h2>
            <p><strong>Subject:</strong> {subject}</p>
            <p><strong>Time:</strong> {time_str}</p>
            <p><strong>Meeting Link:</strong> <a href="{meeting_link}">{meeting_link}</a></p>
            <br>
            <div style="display: flex; gap: 10px;">
                <a href="{magic_link_t}" style="background-color: #4CAF50; color: white; padding: 15px 32px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; border-radius: 5px; margin-right: 10px;">
                    ▶️ JOIN CLASS
                </a>
                <a href="{magic_link_end}" style="background-color: #f44336; color: white; padding: 15px 32px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; border-radius: 5px;">
                    ⏹️ END CLASS & SURVEY
                </a>
            </div>
            <p style="color: #666; font-size: 12px; margin-top: 20px;">
                <b>Instructions:</b><br>
                1. Click 'JOIN CLASS' exactly when you enter the Google Meet. This records your log-in time.<br>
                2. Click 'END CLASS & SURVEY' when the class finishes. This records the completion time and opens the mandatory survey.
            </p>
        </div>
        """
        msg_t.attach(MIMEText(body_t, 'html'))
        server.sendmail(SENDER_EMAIL, teacher_email, msg_t.as_string())
        
        # 2. Send to Students
        for s_name, s_email in student_emails:
            msg_s = MIMEMultipart()
            msg_s['From'] = SENDER_EMAIL
            msg_s['To'] = s_email
            msg_s['Subject'] = f"Class Invitation: {subject} @ {time_str}"
            
            magic_link_s = f"{BASE_APP_URL}/?action=clock_in&session_id={session_id}&role=Student&student_name={s_name}"
            
            body_s = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <h2 style="color: #2196F3;">PAS Tutors Class Invitation</h2>
                <p><strong>Subject:</strong> {subject}</p>
                <p><strong>Time:</strong> {time_str}</p>
                <p><strong>Meeting Link:</strong> <a href="{meeting_link}">{meeting_link}</a></p>
                <br>
                <a href="{magic_link_s}" style="background-color: #2196F3; color: white; padding: 15px 32px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; border-radius: 5px;">
                    ▶️ JOIN CLASS
                </a>
                <p style="color: #666; font-size: 12px; margin-top: 20px;">Clicking this link will automatically clock you in and open the meeting.</p>
            </div>
            """
            msg_s.attach(MIMEText(body_s, 'html'))
            server.sendmail(SENDER_EMAIL, s_email, msg_s.as_string())
        
        server.quit()
        return True, "Invites Sent Successfully"
    except Exception as e:
        print(f"Email Error: {e}")
        return False, str(e)


@st.cache_data(ttl=300)
def get_sessions_data(_client):
    sheet = get_sheet_by_id(_client)
    if sheet:
        try:
            # Check for worksheet existence explicitly
            ws_list = sheet.worksheets()
            ws_names = [ws.title for ws in ws_list]
            
            if "Sessions" not in ws_names:
                # Updated Columns for Phase 2 Refactor
                cols = ["Session ID", "Teacher Name", "Student Name", "Subject", "Scheduled Time", "Meeting Link", "Status", "Attendance Code", "Teacher Join", "Student Join", "Actual End"]
                ws = sheet.add_worksheet(title="Sessions", rows="1000", cols="20")
                ws.append_row(cols)
                return pd.DataFrame(columns=cols)
            
            worksheet = sheet.worksheet("Sessions")
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
        except Exception as e:
            # If get_all_records fails (e.g. empty sheet), return empty DF
            return pd.DataFrame()
            
    return pd.DataFrame()

def schedule_class(client, teacher_name, student_names, subject, time_str, duration_str, meeting_link):
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            # Ensure Sessions tab exists
            get_sessions_data(client) 
            
            ws = sheet.worksheet("Sessions")
            session_id = str(uuid.uuid4())
            
            code = str(random.randint(100000, 999999))
            
            # 1. Parse Time and Duration for Google Meet
            try:
                # time_str is from f"{sc_date} {sc_time}" e.g., '2026-05-16 09:00:00'
                start_dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Handle cases where seconds might be omitted
                start_dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                
            duration_map = {
                "30 Mins": 30, "45 Mins": 45, "1 Hour": 60, "1.5 Hours": 90, "2 Hours": 120
            }
            duration_mins = duration_map.get(duration_str, 60)
            end_dt = start_dt + datetime.timedelta(minutes=duration_mins)
            
            # 2. Fetch Teacher Email
            t_email = ""
            df_t = get_teacher_data(client)
            if not df_t.empty and "Teacher Name" in df_t.columns and "Email" in df_t.columns:
                matches = df_t[df_t["Teacher Name"] == teacher_name]
                if not matches.empty: t_email = matches.iloc[0]["Email"]

            if not t_email:
                 return False, f"Missing Email for Teacher: {teacher_name}", None

            # 3. Fetch Student Emails
            df_s = get_students_data(client)
            student_emails = []
            for s_name in student_names:
                s_email = ""
                if not df_s.empty and "Student Name" in df_s.columns and "Email" in df_s.columns:
                    matches = df_s[df_s["Student Name"] == s_name]
                    if not matches.empty: s_email = matches.iloc[0]["Email"]
                if s_email:
                    student_emails.append((s_name, s_email))
            
            if not student_emails:
                return False, "No valid students found to schedule.", None

            # 4. Auto-generate Meet Link if blank (with attendees to skip lobby)
            if not meeting_link or not meeting_link.strip():
                # Compile list of all emails for the calendar invite
                attendees = [t_email] + [email for name, email in student_emails]
                generated_link = generate_meet_link(subject, start_dt, end_dt, attendees)
                if generated_link:
                    meeting_link = generated_link
                else:
                    return False, "Failed to generate Google Meet link. Have you authorized the app yet?", None
                    
            # 5. Insert Rows
            rows_to_add = []
            for s_name, s_email in student_emails:
                rows_to_add.append([
                    session_id, teacher_name, s_name, subject, str(time_str), 
                    meeting_link, "Scheduled", code, "", "", ""
                ])
                
            ws.append_rows(rows_to_add)
            
            # 5. Send Emails
            email_errors = []
            # Send ONE email to teacher containing clock-in and clock-out links
            # We will modify send_email_invite slightly to just take lists or call it in a loop
            # Wait, currently send_email_invite sends to 1 teacher and 1 student. 
            # We will call a modified or new function for all students.
            
            email_success, email_msg = send_multi_email_invite(t_email, student_emails, subject, time_str, session_id, meeting_link)
            
            get_sessions_data.clear()
            if email_success:
                return True, "Class Scheduled & Invites Sent Successfully!", session_id
            else:
                return True, f"Class Scheduled but Email Failed: {email_msg}", session_id
            
        except Exception as e:
            st.error(f"Error scheduling class: {e}")
            return False, str(e), None
    return False, "No Sheet", None

def clock_in_by_id(client, session_id, role, student_name=None):
    """
    Magic Link Clock-in using Session ID.
    Returns: Success (Bool), Message (Str), Meeting Link (Str)
    """
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            ws = sheet.worksheet("Sessions")
            cells = ws.findall(session_id)
            if cells:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                meeting_link = ""
                updated_any = False
                
                for cell in cells:
                    row = cell.row
                    # Verify Status
                    status = ws.cell(row, 7).value # Col 7: Status
                    if status not in ["Scheduled", "In-Progress"]:
                        continue # Skip completed rows
                    
                    meeting_link = ws.cell(row, 6).value # Col 6: Link
                    
                    if role == "Teacher":
                        ws.update_cell(row, 9, now) # Col 9: Teacher Join
                        ws.update_cell(row, 7, "In-Progress")
                        updated_any = True
                    elif role == "Student":
                        # Only update if student name matches
                        row_student = ws.cell(row, 3).value # Col 3: Student Name
                        if not student_name or row_student.lower() == student_name.lower():
                            ws.update_cell(row, 10, now) # Col 10: Student Join
                            ws.update_cell(row, 7, "In-Progress")
                            updated_any = True
                
                if updated_any:
                    get_sessions_data.clear()
                    return True, "Clocked In Successfully!", meeting_link
                else:
                    return False, "Could not find a valid class to clock in to (it may be completed or student name mismatch).", ""
            else:
                return False, "Session Not Found", ""
        except Exception as e:
            return False, str(e), ""
    return False, "Error", ""

def clock_in(client, code, user_name, role):
    """
    Independent Clock-in.
    Role: 'Teacher' or 'Student'
    """
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            ws = sheet.worksheet("Sessions")
            records = ws.get_all_records()
            
            for i, record in enumerate(records):
                row_num = i + 2
                # Match Code
                if str(record["Attendance Code"]) == str(code):
                    # Check Status
                    if record["Status"] in ["Scheduled", "In-Progress"]:
                        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Verify Name (Security)
                        expected_name = record["Teacher Name"] if role == "Teacher" else record["Student Name"]
                        # Loose match or strict? Strict for now.
                        if user_name.lower() not in expected_name.lower() and expected_name.lower() not in user_name.lower():
                             return False, f"Name mismatch. Code belongs to {expected_name}."

                        # Update Time
                        if role == "Teacher":
                            ws.update_cell(row_num, 9, now) # Teacher Join Col
                        else:
                            ws.update_cell(row_num, 10, now) # Student Join Col
                            
                        # Update Status to In-Progress if not already
                        ws.update_cell(row_num, 7, "In-Progress") # Status Col (Index 7 based on new struct? Wait.)
                        # Columns: 
                        # 1:ID, 2:T, 3:S, 4:Sub, 5:Time, 6:Link, 7:Status, 8:Code, 9:T_Join, 10:S_Join
                        
                        get_sessions_data.clear()
                        return True, f"Clock-in Successful for {role}!"
                    else:
                        return False, "Class already completed or cancelled."
            return False, "Invalid Code"
        except Exception as e:
            return False, str(e)
    return False, "Error"

def end_class_v2(client, session_id):
    """
    Ends class. Logs to reviews.
    """
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            ws = sheet.worksheet("Sessions")
            cell = ws.find(session_id)
            if cell:
                row = cell.row
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Update Status (Col 7) -> Completed
                ws.update_cell(row, 7, "Completed")
                ws.update_cell(row, 11, now) # End Time
                
                # Fetch info for billing
                t_name = ws.cell(row, 2).value
                s_name = ws.cell(row, 3).value
                
                add_review(client, t_name, s_name, "Class Completed (Session System)")
                get_sessions_data.clear()
                return True
        except Exception as e:
            st.error(f"Error ending: {e}")
    return False

def update_student(client, original_name, updated_data):
    """
    Updates student details in 'Students' tab.
    updated_data keys: Name, Email, Phone, Subjects, Class Times
    """
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            ws = sheet.worksheet("Students")
            cell = ws.find(original_name)
            if cell:
                r = cell.row
                # Update specific columns.
                # Col 1: Name, 2: Email, 3: Phone, 4: Class Times, 5: Subjects
                
                updates = [
                    updated_data.get("Name"),
                    updated_data.get("Email"),
                    updated_data.get("Phone"),
                    updated_data.get("Class Times"),
                    updated_data.get("Subjects")
                ]
                
                # Batch update for efficiency? Or separate calls. 
                # range "A{r}:E{r}"
                ws.update(f"A{r}:E{r}", [updates])
                
                # If Name Changed, we should try to update Billing too to keep sync
                if original_name != updated_data.get("Name"):
                    try:
                        ws_billing = sheet.worksheet("Billing")
                        b_cell = ws_billing.find(original_name)
                        if b_cell:
                            ws_billing.update_cell(b_cell.row, 1, updated_data.get("Name"))
                    except:
                        pass # Fail silently on billing sync if complex
                
                # Clear relevant caches
                get_students_data.clear()
                get_billing_data.clear()
                
                # Sync teacher assignments (add/remove this student from their Assigned Students lists)
                if "Selected Teachers" in updated_data:
                    sync_student_to_teachers(client, updated_data.get("Name"), updated_data.get("Selected Teachers"))
                
                # Sync teacher schedule based on new class times
                sync_teacher_schedule_from_student(client, updated_data.get("Name"))
                
                return True, "Student updated successfully!"
            else:
                return False, "Student not found."
        except Exception as e:
            return False, str(e)
    return False, "No Sheet"

def sync_student_to_teachers(client, student_name, selected_teachers):
    """
    Ensures that the student is strictly in the 'Assigned Students' list 
    of the chosen teachers, and removed from any others.
    """
    try:
        df_teachers = get_teacher_data(client)
        if df_teachers.empty: return False
        
        sheet = get_sheet_by_id(client)
        ws_teachers = sheet.worksheet("Teachers")
        
        student_norm = student_name.strip().lower()
        
        for idx, t_row in df_teachers.iterrows():
            t_name = str(t_row.get("Teacher Name", ""))
            if not t_name: continue
            
            assigned_raw = str(t_row.get("Assigned Students", ""))
            assigned_list = [a.strip() for a in assigned_raw.split(",") if a.strip()]
            assigned_norm = [a.lower() for a in assigned_list]
            
            needs_update = False
            
            if t_name in selected_teachers:
                # Should be assigned
                if student_norm not in assigned_norm:
                    assigned_list.append(student_name.strip())
                    needs_update = True
            else:
                # Should NOT be assigned
                if student_norm in assigned_norm:
                    assigned_list = [a for a in assigned_list if a.lower() != student_norm]
                    needs_update = True
                    
            if needs_update:
                final_assigned_str = ", ".join(assigned_list)
                t_cell = ws_teachers.find(t_name)
                if t_cell:
                    ws_teachers.update_cell(t_cell.row, 5, final_assigned_str) # Column E is assigned students
                    
        get_teacher_data.clear()
        return True
    except Exception as e:
        print(f"Error syncing student to teachers: {e}")
        return False

def sync_teacher_schedule_from_student(client, student_name):
    """
    Rebuilds the schedule of any teacher assigned to this student, 
    based on the class times of all their assigned students.
    """
    try:
        df_teachers = get_teacher_data(client)
        df_students = get_students_data(client)
        
        if df_teachers.empty or df_students.empty: return False
        
        student_name_norm = student_name.strip().lower()
        
        teachers_to_update = []
        for idx, t_row in df_teachers.iterrows():
            assigned = str(t_row.get("Assigned Students", ""))
            assigned_list = [a.strip().lower() for a in assigned.split(",") if a.strip()]
            if student_name_norm in assigned_list:
                teachers_to_update.append(t_row.get("Teacher Name"))
                
        if not teachers_to_update: return True 
        
        sheet = get_sheet_by_id(client)
        ws_teachers = sheet.worksheet("Teachers")
        
        for t_name in teachers_to_update:
            t_row = df_teachers[df_teachers["Teacher Name"] == t_name].iloc[0]
            assigned_raw = str(t_row.get("Assigned Students", ""))
            assigned_list_norm = [a.strip().lower() for a in assigned_raw.split(",") if a.strip()]
            
            teacher_schedule_parts = []
            
            for s_norm in assigned_list_norm:
                s_match = df_students[df_students["Student Name"].str.strip().str.lower() == s_norm]
                if not s_match.empty:
                    s_times = str(s_match.iloc[0].get("Class Times", ""))
                    if s_times:
                        parts = [p.strip() for p in s_times.split(",") if p.strip()]
                        teacher_schedule_parts.extend(parts)
            
            final_schedule_str = ", ".join(teacher_schedule_parts) if teacher_schedule_parts else "Not Specified"
            
            t_cell = ws_teachers.find(t_name)
            if t_cell:
                ws_teachers.update_cell(t_cell.row, 6, final_schedule_str)
                
        get_teacher_data.clear()
        return True
    except Exception as e:
        print(f"Error syncing teacher schedule: {e}")
        return False

def update_teacher(client, original_name, updated_data):
    """
    Updates teacher details in 'Teachers' tab.
    updated_data keys: Name, Email, Phone, Expertise, Assigned Students, Availability
    """
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            ws = sheet.worksheet("Teachers")
            cell = ws.find(original_name)
            if cell:
                r = cell.row
                # Col 1: Name, 2: Email, 3: Phone, 4: Expertise, 5: Assigned, 6: Schedule
                
                updates = [
                    updated_data.get("Name"),
                    updated_data.get("Email"),
                    updated_data.get("Phone"),
                    updated_data.get("Expertise"),
                    updated_data.get("Assigned Students"),
                    updated_data.get("Availability")
                ]
                
                ws.update(f"A{r}:F{r}", [updates])
                
                # Clear relevant caches
                get_teacher_data.clear()
                
                return True, "Teacher updated successfully!"
            else:
                return False, "Teacher not found."
        except Exception as e:
            return False, str(e)
    return False, "No Sheet"


# --- GOOGLE MEET API (OAUTH 2.0) ---
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

def generate_meet_link(subject, start_dt, end_dt, attendees_emails=None):
    """
    Creates a Calendar event with a Hangouts Meet link.
    start_dt and end_dt must be datetime objects.
    """
    # Helper to find secret either at root or nested under gcp_service_account
    def get_oauth_secret(key_name):
        if key_name in st.secrets:
            return st.secrets[key_name]
        elif "gcp_service_account" in st.secrets and key_name in st.secrets["gcp_service_account"]:
            return st.secrets["gcp_service_account"][key_name]
        return None

    client_secret_data = get_oauth_secret("GOOGLE_OAUTH_CLIENT_SECRET")
    if client_secret_data:
        with open("client_secret.json", "w") as f:
            f.write(client_secret_data)
            
    token_data = get_oauth_secret("GOOGLE_OAUTH_TOKEN")
    if token_data:
        with open("token.json", "w") as f:
            f.write(token_data)
            
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('client_secret.json'):
                st.error("Missing client_secret.json for Google Meet integration.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    try:
        service = build('calendar', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error building Calendar service: {e}")
        return None
    
    if not service:
        return None
    
    # Format for Google Calendar (RFC3339)
    # Using local timezone (assuming system time is correct for the user)
    # The user has NGN currency, so Africa/Lagos is likely, but using local ISO format is safer.
    start_str = start_dt.isoformat()
    end_str = end_dt.isoformat()
    
    event = {
        'summary': f"PAS Class: {subject}",
        'start': {
            'dateTime': start_str,
            'timeZone': 'Africa/Lagos', 
        },
        'end': {
            'dateTime': end_str,
            'timeZone': 'Africa/Lagos',
        },
        'conferenceData': {
            'createRequest': {
                'requestId': str(uuid.uuid4()),
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        }
    }
    
    if attendees_emails:
        event['attendees'] = [{'email': email} for email in attendees_emails]
        
    try:
        event = service.events().insert(calendarId='primary', body=event, conferenceDataVersion=1, sendUpdates='none').execute()
        meet_link = event.get('hangoutLink')
        return meet_link
    except Exception as e:
        print(f"Error creating Meet link: {e}")
        st.error(f"Error creating Google Meet link: {e}")
        return None
def submit_survey(client, session_id, survey_data):
    """
    Submits the end-of-class survey, updates Sessions, and adds a legacy review for billing.
    """
    sheet = get_sheet_by_id(client)
    if not sheet: return False, "No Sheet"
    
    try:
        # 1. Update Sessions Sheet (Close the class)
        ws_sessions = sheet.worksheet("Sessions")
        cells = ws_sessions.findall(session_id)
        if not cells:
            return False, "Session not found."
            
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        teacher_name = ""
        students = []
        subject = ""
        
        for cell in cells:
            row = cell.row
            ws_sessions.update_cell(row, 7, "Completed") # Col 7: Status
            ws_sessions.update_cell(row, 11, now) # Col 11: Actual End
            
            if not teacher_name:
                teacher_name = ws_sessions.cell(row, 2).value
                subject = ws_sessions.cell(row, 4).value
            
            s_name = ws_sessions.cell(row, 3).value
            if s_name: students.append(s_name)
            
        get_sessions_data.clear()
        
        # 2. Add to Surveys Sheet
        ws_list = sheet.worksheets()
        ws_names = [w.title for w in ws_list]
        if "Surveys" not in ws_names:
            cols = ["Timestamp", "Session ID", "Teacher", "Subject", "Students", "Topic Taught", "Learning Outcome", "Learner's Behaviour", "Learner's Participation", "Assignment Given", "Last Assignment Done"]
            ws_surveys = sheet.add_worksheet(title="Surveys", rows="1000", cols="20")
            ws_surveys.append_row(cols)
        else:
            ws_surveys = sheet.worksheet("Surveys")
            
        students_str = ", ".join(students)
        
        row_data = [
            now, session_id, teacher_name, subject, students_str,
            survey_data.get("Topic Taught", ""),
            survey_data.get("Learning Outcome", ""),
            survey_data.get("Learner's Behaviour", ""),
            survey_data.get("Learner's Participation", ""),
            survey_data.get("Assignment Given", ""),
            survey_data.get("Last Assignment Done", "")
        ]
        ws_surveys.append_row(row_data)
        
        # 3. Add to Legacy Reviews Sheet (for billing)
        # We add one review per student so calculate_teacher_pay counts each student's class
        topic_taught = survey_data.get("Topic Taught", "")
        for s_name in students:
            add_review(client, teacher_name, s_name, f"Class Completed via Survey - {subject} ({topic_taught})")
            
        return True, "Success"
    except Exception as e:
        return False, str(e)


# ==========================================
# TEACHER PORTAL & WEEKLY PLANS HELPERS
# ==========================================

def normalize_name(name):
    """
    Normalizes a name string by collapsing multiple spaces, trimming, and lowercasing.
    E.g. 'Kyrie  Amana ' -> 'kyrie amana'
    """
    if not name or pd.isna(name):
        return ""
    return re.sub(r'\s+', ' ', str(name)).strip().lower()

def get_current_week_range(target_date=None, shift_on_weekend=True):
    """
    Returns string formatted as: 'Sep 14 - Sep 20, 2026'.
    On Saturday (weekday 5) and Sunday (weekday 6), shifts to the upcoming week (next Mon-Sun) for planning.
    """
    if target_date is None:
        target_date = datetime.date.today()
        
    if shift_on_weekend and target_date.weekday() >= 5: # Saturday or Sunday
        days_ahead = 7 - target_date.weekday()
        monday = target_date + datetime.timedelta(days=days_ahead)
    else:
        monday = target_date - datetime.timedelta(days=target_date.weekday())
        
    sunday = monday + datetime.timedelta(days=6)
    return f"{monday.strftime('%b %d')} - {sunday.strftime('%b %d, %Y')}"

def get_available_planning_weeks(target_date=None):
    """
    Returns planning weeks dictionary:
    - active_week: Default week (next week if Sat/Sun, else current week)
    - current_week: Mon-Sun of current week
    - upcoming_week: Mon-Sun of next week
    - is_weekend: True if Saturday or Sunday
    """
    if target_date is None:
        target_date = datetime.date.today()
        
    is_weekend = (target_date.weekday() >= 5)
    cur_monday = target_date - datetime.timedelta(days=target_date.weekday())
    cur_sunday = cur_monday + datetime.timedelta(days=6)
    cur_week_str = f"{cur_monday.strftime('%b %d')} - {cur_sunday.strftime('%b %d, %Y')}"
    
    next_monday = cur_monday + datetime.timedelta(days=7)
    next_sunday = next_monday + datetime.timedelta(days=6)
    next_week_str = f"{next_monday.strftime('%b %d')} - {next_sunday.strftime('%b %d, %Y')}"
    
    active_week = next_week_str if is_weekend else cur_week_str
    
    return {
        "active_week": active_week,
        "current_week": cur_week_str,
        "upcoming_week": next_week_str,
        "is_weekend": is_weekend
    }

def generate_teacher_portal_link(teacher_name, base_url=None):
    """
    Generates direct portal link for a teacher.
    """
    base = base_url or BASE_APP_URL
    base = base.rstrip('/')
    clean_name = re.sub(r'\s+', ' ', str(teacher_name)).strip()
    encoded_name = urllib.parse.quote_plus(clean_name)
    return f"{base}/?portal=teacher&t={encoded_name}"

@st.cache_data(ttl=300)
@retry_on_quota
def get_weekly_plans_data(_client):
    """
    Fetches all weekly confirmation and lesson plan records from 'Weekly_Plans' tab.
    """
    sheet = get_sheet_by_id(_client)
    if sheet:
        try:
            ws_list = sheet.worksheets()
            ws_names = [w.title for w in ws_list]
            cols = ["Plan ID", "Week Range", "Teacher Name", "Student Name", "Subject", "Confirmed Class Time", "Topic / Curriculum", "Meeting Link", "Status", "Last Updated"]
            if "Weekly_Plans" not in ws_names:
                ws = sheet.add_worksheet(title="Weekly_Plans", rows="1000", cols="20")
                ws.append_row(cols)
                return pd.DataFrame(columns=cols)
            ws = sheet.worksheet("Weekly_Plans")
            data = ws.get_all_records()
            return pd.DataFrame(data)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def save_weekly_plan(client, week_range, teacher_name, student_name, subject, confirmed_time, topic, meeting_link, status="Confirmed"):
    """
    Saves or updates a teacher's weekly plan for a student in 'Weekly_Plans' tab.
    Uses normalize_name for robust row matching.
    """
    sheet = get_sheet_by_id(client)
    if not sheet:
        return False, "Google Sheet client not connected."
    try:
        get_weekly_plans_data(client)
        ws = sheet.worksheet("Weekly_Plans")
        records = ws.get_all_records()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        target_row = None
        clean_target_week = normalize_name(week_range)
        clean_target_teacher = normalize_name(teacher_name)
        clean_target_student = normalize_name(student_name)
        
        for idx, r in enumerate(records, start=2): # 1-indexed, header is row 1
            r_week = normalize_name(r.get("Week Range", ""))
            r_teacher = normalize_name(r.get("Teacher Name", ""))
            r_student = normalize_name(r.get("Student Name", ""))
            
            if (r_week == clean_target_week and 
                r_teacher == clean_target_teacher and 
                r_student == clean_target_student):
                target_row = idx
                break
                
        clean_time = str(confirmed_time).strip()
        clean_topic = str(topic).strip()
        clean_link = str(meeting_link).strip()
        clean_subject = str(subject).strip()
        canonical_teacher = re.sub(r'\s+', ' ', str(teacher_name)).strip()
        canonical_student = re.sub(r'\s+', ' ', str(student_name)).strip()
        
        if target_row:
            # Columns: 1: Plan ID, 2: Week Range, 3: Teacher Name, 4: Student Name, 5: Subject, 6: Confirmed Class Time, 7: Topic / Curriculum, 8: Meeting Link, 9: Status, 10: Last Updated
            ws.update_cell(target_row, 5, clean_subject)
            ws.update_cell(target_row, 6, clean_time)
            ws.update_cell(target_row, 7, clean_topic)
            ws.update_cell(target_row, 8, clean_link)
            ws.update_cell(target_row, 9, status)
            ws.update_cell(target_row, 10, now_str)
        else:
            plan_id = str(uuid.uuid4())[:8]
            row_data = [
                plan_id, str(week_range), canonical_teacher, canonical_student,
                clean_subject, clean_time, clean_topic, clean_link, status, now_str
            ]
            ws.append_row(row_data)
            
        if hasattr(get_weekly_plans_data, "clear"):
            get_weekly_plans_data.clear()
        return True, "Plan saved successfully!"
    except Exception as e:
        return False, f"Error saving plan: {e}"

def get_teacher_assigned_students_details(client, teacher_name, week_range=None):
    """
    Returns a list of dicts for each student assigned to teacher_name.
    Combines info from 'Teachers', 'Students', and 'Weekly_Plans' tabs.
    Robustly handles whitespace, casing, and dual-direction mappings.
    """
    if week_range is None:
        week_range = get_current_week_range()
        
    df_teachers = get_teacher_data(client)
    if df_teachers.empty or "Teacher Name" not in df_teachers.columns:
        return []
        
    clean_target_t = normalize_name(teacher_name)
    
    # Match teacher with normalize_name
    t_match = df_teachers[df_teachers["Teacher Name"].apply(normalize_name) == clean_target_t]
    if t_match.empty:
        return []
        
    t_row = t_match.iloc[0]
    assigned_raw = str(t_row.get("Assigned Students", ""))
    raw_student_names = [s.strip() for s in assigned_raw.split(",") if s.strip()]
    
    if not raw_student_names:
        return []
        
    df_students = get_students_data(client)
    df_plans = get_weekly_plans_data(client)
    
    results = []
    seen_students_norm = set()
    
    for s_name in raw_student_names:
        s_norm = normalize_name(s_name)
        if not s_norm or s_norm in seen_students_norm:
            continue
        seen_students_norm.add(s_norm)
        
        # Default display name cleaned
        display_name = re.sub(r'\s+', ' ', str(s_name)).strip()
        
        s_info = {
            "Student Name": display_name,
            "Email": "",
            "Phone": "",
            "Class Times": "",
            "Subjects": "",
            "Academic Progress": "N/A",
            "Attendance": "N/A",
            "Payment Status": "N/A",
            "Current Week Plan": {}
        }
        
        if not df_students.empty and "Student Name" in df_students.columns:
            s_match = df_students[df_students["Student Name"].apply(normalize_name) == s_norm]
            if not s_match.empty:
                s_row = s_match.iloc[0]
                canonical_name = re.sub(r'\s+', ' ', str(s_row.get("Student Name", ""))).strip()
                if canonical_name:
                    s_info["Student Name"] = canonical_name
                s_info["Email"] = str(s_row.get("Email", "")).strip()
                s_info["Phone"] = str(s_row.get("Phone Number") or s_row.get("Phone") or "").strip()
                s_info["Class Times"] = str(s_row.get("Class Times", "")).strip()
                s_info["Subjects"] = str(s_row.get("Subjects", "")).strip()
                s_info["Academic Progress"] = s_row.get("Academic Progress", "N/A")
                s_info["Attendance"] = s_row.get("Attendance", "N/A")
                s_info["Payment Status"] = s_row.get("Payment Status", "N/A")
                
        if not df_plans.empty and "Week Range" in df_plans.columns:
            p_match = df_plans[
                (df_plans["Week Range"].apply(normalize_name) == normalize_name(week_range)) &
                (df_plans["Teacher Name"].apply(normalize_name) == clean_target_t) &
                (df_plans["Student Name"].apply(normalize_name) == s_norm)
            ]
            if not p_match.empty:
                s_info["Current Week Plan"] = p_match.iloc[0].to_dict()
                
        results.append(s_info)
        
    return results


# ==========================================
# CLASS SESSION REPORTS & MONTHLY EVALUATIONS
# ==========================================

BOT_REPORTS_DIR_CANDIDATES = [
    r"c:\Users\user\Documents\antigravity\quick-raman\meeting-bot\recordings\reports",
    os.path.join(os.path.expanduser("~"), "Documents", "antigravity", "quick-raman", "meeting-bot", "recordings", "reports"),
    os.path.join(os.getcwd(), "recordings", "reports")
]

CLASS_REPORTS_COLS = [
    "Report ID", "Session ID", "Date", "Student Name", "Teacher Name", "Subject", 
    "Topic", "Duration", "Executive Summary", "Curriculum Breakdown", "Homework Tracking", 
    "Student Interaction", "Teacher Engagement", "Anomalies", "Social Highlights", 
    "File Name", "Status", "Last Modified"
]

MONTHLY_REPORTS_COLS = [
    "Monthly Report ID", "Month", "Student Name", "Teacher Name", "Subject", 
    "Total Classes", "Total Hours", "Curriculum Covered", "Homework Rating", 
    "Comprehension & Progress", "Teacher Remarks", "Head Teacher Recommendations", 
    "Status", "Teacher Confirmed At", "Head Teacher Approved At", "Last Modified", 
    "Associated Report IDs"
]

def get_bot_reports_directory():
    """Returns the local path to meeting-bot/recordings/reports if it exists."""
    for p in BOT_REPORTS_DIR_CANDIDATES:
        if os.path.exists(p):
            return p
    return None

def _safe_json_dumps(obj):
    if isinstance(obj, (dict, list)):
        try:
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return str(obj)
    return str(obj or "")

def _safe_json_loads(val, default_val=None):
    if default_val is None:
        default_val = {}
    if not val or pd.isna(val):
        return default_val
    if isinstance(val, (dict, list)):
        return val
    s = str(val).strip()
    if not s:
        return default_val
    try:
        return json.loads(s)
    except Exception:
        return default_val

@st.cache_data(ttl=120)
def get_class_reports_data(_client):
    """
    Fetches all individual class session reports from 'Class_Reports' Google Sheet.
    Also synchronizes any local report JSON files found in meeting-bot/recordings/reports.
    """
    sheet = get_sheet_by_id(_client)
    if not sheet:
        return pd.DataFrame(columns=CLASS_REPORTS_COLS)

    try:
        ws_list = [w.title for w in sheet.worksheets()]
        if "Class_Reports" not in ws_list:
            ws = sheet.add_worksheet(title="Class_Reports", rows="1000", cols="25")
            ws.append_row(CLASS_REPORTS_COLS)
            records = []
        else:
            ws = sheet.worksheet("Class_Reports")
            records = ws.get_all_records()

        df = pd.DataFrame(records)
        for col in CLASS_REPORTS_COLS:
            if col not in df.columns:
                df[col] = ""

        # Auto-ingest local bot report files if available
        local_dir = get_bot_reports_directory()
        if local_dir and os.path.isdir(local_dir):
            existing_files = set(df["File Name"].astype(str).str.strip().tolist()) if not df.empty else set()
            new_rows = []
            
            for fname in os.listdir(local_dir):
                if fname.startswith("report_") and fname.endswith(".json"):
                    full_p = os.path.join(local_dir, fname)
                    try:
                        with open(full_p, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            
                        orig_file = data.get("fileName", fname)
                        if orig_file in existing_files or fname in existing_files:
                            continue
                            
                        rep_inner = data.get("report", {})
                        overview = rep_inner.get("sessionOverview", {})
                        
                        r_id = str(uuid.uuid4())
                        s_id = data.get("sessionId", "")
                        d_str = str(overview.get("date") or datetime.date.today().strftime("%Y-%m-%d"))
                        st_name = str(overview.get("studentName", "")).strip()
                        tc_name = str(overview.get("teacherName", "")).strip()
                        subj = str(overview.get("subject", "")).strip()
                        topic = str(overview.get("topic", "")).strip()
                        dur = str(overview.get("duration", "60 mins"))
                        exec_sum = str(overview.get("executiveSummary", "")).strip()
                        
                        curriculum = _safe_json_dumps(rep_inner.get("curriculumBreakdown", {}))
                        hw = _safe_json_dumps(rep_inner.get("homeworkTracking", {}))
                        interaction = _safe_json_dumps(rep_inner.get("studentInteraction", {}))
                        teacher_eng = _safe_json_dumps(rep_inner.get("teacherEngagement", {}))
                        anomalies = _safe_json_dumps(rep_inner.get("anomaliesAndDisruptions", {}))
                        social = _safe_json_dumps(rep_inner.get("socialMediaHighlights", {}))
                        
                        now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        new_row = [
                            r_id, s_id, d_str, st_name, tc_name, subj, topic, dur, exec_sum,
                            curriculum, hw, interaction, teacher_eng, anomalies, social,
                            orig_file, "Generated", now_ts
                        ]
                        new_rows.append(new_row)
                        existing_files.add(orig_file)
                    except Exception as parse_e:
                        print(f"Error parsing local report {fname}: {parse_e}")
                        
            if new_rows:
                ws.append_rows(new_rows)
                # Re-fetch records
                records = ws.get_all_records()
                df = pd.DataFrame(records)

        return df

    except Exception as e:
        st.error(f"Error fetching Class_Reports: {e}")
        return pd.DataFrame(columns=CLASS_REPORTS_COLS)


def save_class_report(client, report_data):
    """
    Saves or updates an individual class session report in Google Sheet 'Class_Reports'.
    Also updates local JSON report file if present.
    """
    sheet = get_sheet_by_id(client)
    if not sheet:
        return False, "Google Sheet client not connected."

    try:
        # Ensure sheet exists
        get_class_reports_data(client)
        ws = sheet.worksheet("Class_Reports")
        
        report_id = str(report_data.get("Report ID") or "").strip()
        now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_data["Last Modified"] = now_ts
        
        row_values = [
            report_data.get("Report ID") or str(uuid.uuid4()),
            report_data.get("Session ID", ""),
            str(report_data.get("Date", "")),
            str(report_data.get("Student Name", "")),
            str(report_data.get("Teacher Name", "")),
            str(report_data.get("Subject", "")),
            str(report_data.get("Topic", "")),
            str(report_data.get("Duration", "60 mins")),
            str(report_data.get("Executive Summary", "")),
            _safe_json_dumps(report_data.get("Curriculum Breakdown", {})),
            _safe_json_dumps(report_data.get("Homework Tracking", {})),
            _safe_json_dumps(report_data.get("Student Interaction", {})),
            _safe_json_dumps(report_data.get("Teacher Engagement", {})),
            _safe_json_dumps(report_data.get("Anomalies", {})),
            _safe_json_dumps(report_data.get("Social Highlights", {})),
            str(report_data.get("File Name", "")),
            str(report_data.get("Status", "Edited")),
            now_ts
        ]
        
        if report_id:
            cells = ws.findall(report_id)
            if cells:
                target_row = cells[0].row
                try:
                    ws.update(f"A{target_row}:R{target_row}", [row_values])
                except Exception:
                    for col_idx, val in enumerate(row_values, start=1):
                        ws.update_cell(target_row, col_idx, str(val))
                get_class_reports_data.clear()
                return True, "Class report updated successfully."

        # If not found or new, append row
        ws.append_row(row_values)
        get_class_reports_data.clear()
        return True, "Class report created successfully."

    except Exception as e:
        return False, f"Failed to save class report: {e}"


@st.cache_data(ttl=120)
def get_monthly_reports_data(_client):
    """
    Fetches all monthly consolidated progress reports from Google Sheet 'Monthly_Reports'.
    """
    sheet = get_sheet_by_id(_client)
    if not sheet:
        return pd.DataFrame(columns=MONTHLY_REPORTS_COLS)

    try:
        ws_list = [w.title for w in sheet.worksheets()]
        if "Monthly_Reports" not in ws_list:
            ws = sheet.add_worksheet(title="Monthly_Reports", rows="1000", cols="20")
            ws.append_row(MONTHLY_REPORTS_COLS)
            return pd.DataFrame(columns=MONTHLY_REPORTS_COLS)

        ws = sheet.worksheet("Monthly_Reports")
        records = ws.get_all_records()
        df = pd.DataFrame(records)
        for col in MONTHLY_REPORTS_COLS:
            if col not in df.columns:
                df[col] = ""
        return df

    except Exception as e:
        st.error(f"Error fetching Monthly_Reports: {e}")
        return pd.DataFrame(columns=MONTHLY_REPORTS_COLS)


def save_monthly_report(client, monthly_data):
    """
    Saves or updates a monthly consolidated report in Google Sheet 'Monthly_Reports'.
    """
    sheet = get_sheet_by_id(client)
    if not sheet:
        return False, "Google Sheet client not connected."

    try:
        get_monthly_reports_data(client)
        ws = sheet.worksheet("Monthly_Reports")
        
        report_id = str(monthly_data.get("Monthly Report ID") or "").strip()
        now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        monthly_data["Last Modified"] = now_ts
        
        if not report_id:
            report_id = str(uuid.uuid4())
            monthly_data["Monthly Report ID"] = report_id

        row_values = [
            report_id,
            str(monthly_data.get("Month", "")),
            str(monthly_data.get("Student Name", "")),
            str(monthly_data.get("Teacher Name", "")),
            str(monthly_data.get("Subject", "")),
            str(monthly_data.get("Total Classes", 0)),
            str(monthly_data.get("Total Hours", "0")),
            str(monthly_data.get("Curriculum Covered", "")),
            str(monthly_data.get("Homework Rating", "")),
            str(monthly_data.get("Comprehension & Progress", "")),
            str(monthly_data.get("Teacher Remarks", "")),
            str(monthly_data.get("Head Teacher Recommendations", "")),
            str(monthly_data.get("Status", "Draft")),
            str(monthly_data.get("Teacher Confirmed At", "")),
            str(monthly_data.get("Head Teacher Approved At", "")),
            now_ts,
            str(monthly_data.get("Associated Report IDs", ""))
        ]

        cells = ws.findall(report_id)
        if cells:
            target_row = cells[0].row
            try:
                ws.update(f"A{target_row}:Q{target_row}", [row_values])
            except Exception:
                for col_idx, val in enumerate(row_values, start=1):
                    ws.update_cell(target_row, col_idx, str(val))
            get_monthly_reports_data.clear()
            return True, "Monthly report updated successfully."
        else:
            ws.append_row(row_values)
            get_monthly_reports_data.clear()
            return True, "Monthly report saved successfully."

    except Exception as e:
        return False, f"Failed to save monthly report: {e}"


def generate_monthly_report_draft(client, student_name, target_month=None):
    """
    Aggregates all individual class reports for a student for the specified month (e.g. 'October 2026').
    Builds a synthesized monthly report draft with topics, homework consistency, comprehension,
    and draft remarks ready for teacher review.
    """
    if not target_month:
        target_month = datetime.date.today().strftime("%B %Y")  # e.g. "October 2026"

    # Normalize student name
    s_norm = normalize_name(student_name)
    df_classes = get_class_reports_data(client)
    
    # Filter class reports for this student
    matched_classes = pd.DataFrame()
    if not df_classes.empty and "Student Name" in df_classes.columns:
        matched_classes = df_classes[df_classes["Student Name"].apply(normalize_name) == s_norm]

    # Filter by month if date column exists
    filtered_by_month = []
    month_parts = target_month.split()
    target_month_name = month_parts[0].lower() if len(month_parts) > 0 else ""
    target_year = month_parts[1] if len(month_parts) > 1 else str(datetime.date.today().year)

    for idx, row in matched_classes.iterrows():
        d_val = str(row.get("Date", "")).strip()
        include = False
        try:
            dt = datetime.datetime.strptime(d_val[:10], "%Y-%m-%d")
            if dt.strftime("%B").lower() == target_month_name and str(dt.year) == target_year:
                include = True
        except Exception:
            if target_month_name in d_val.lower() or f"{target_year}-10" in d_val:
                include = True
        if include:
            filtered_by_month.append(row)

    if filtered_by_month:
        df_target = pd.DataFrame(filtered_by_month)
    else:
        df_target = matched_classes

    total_classes = len(df_target)
    total_hours = total_classes * 1.0
    
    teachers_list = []
    subjects_list = []
    topics_list = []
    homework_notes = []
    comprehension_notes = []
    associated_ids = []

    for idx, row in df_target.iterrows():
        r_id = str(row.get("Report ID", ""))
        if r_id: associated_ids.append(r_id)
        
        t_name = str(row.get("Teacher Name", "")).strip()
        if t_name and t_name not in teachers_list:
            teachers_list.append(t_name)
            
        subj = str(row.get("Subject", "")).strip()
        if subj and subj not in subjects_list:
            subjects_list.append(subj)
            
        date_str = str(row.get("Date", ""))
        topic = str(row.get("Topic", "")).strip()
        exec_sum = str(row.get("Executive Summary", "")).strip()
        
        if topic:
            topics_list.append(f"• [{date_str}] {topic}: {exec_sum}" if exec_sum else f"• [{date_str}] {topic}")
            
        # Parse homework json
        hw_dict = _safe_json_loads(row.get("Homework Tracking"))
        if hw_dict and isinstance(hw_dict, dict):
            reviewed = hw_dict.get("previousHomeworkReviewed")
            findings = hw_dict.get("previousHomeworkFindings") or ""
            assigned = hw_dict.get("newHomeworkDetails") or ""
            hw_line = f"• [{date_str}] Review: {'Completed' if reviewed else 'Not Set/Pending'}. Findings: {findings}. Task: {assigned}"
            homework_notes.append(hw_line)

        # Parse interaction json
        inter_dict = _safe_json_loads(row.get("Student Interaction"))
        if inter_dict and isinstance(inter_dict, dict):
            eng = inter_dict.get("engagementLevel") or "High"
            comp = inter_dict.get("comprehensionAssessment") or ""
            conf = inter_dict.get("studentConfidence") or "Good"
            interaction_line = f"• [{date_str}] Engagement: {eng} | Confidence: {conf} | Assessment: {comp}"
            comprehension_notes.append(interaction_line)

    curriculum_covered_text = "\n".join(topics_list) if topics_list else "Regular weekly syllabus coverage across assigned modules."
    homework_rating_text = "\n".join(homework_notes) if homework_notes else "Homework assignments consistently set and monitored each session."
    comprehension_text = "\n".join(comprehension_notes) if comprehension_notes else "High engagement observed with steady conceptual mastery."

    teacher_lead = ", ".join(teachers_list) if teachers_list else "PAS Assigned Tutor"
    subject_lead = ", ".join(subjects_list) if subjects_list else "General Academic Tutoring"

    draft_report = {
        "Monthly Report ID": str(uuid.uuid4()),
        "Month": target_month,
        "Student Name": student_name,
        "Teacher Name": teacher_lead,
        "Subject": subject_lead,
        "Total Classes": total_classes,
        "Total Hours": f"{total_hours:.1f}",
        "Curriculum Covered": curriculum_covered_text,
        "Homework Rating": homework_rating_text,
        "Comprehension & Progress": comprehension_text,
        "Teacher Remarks": (
            f"{student_name} has demonstrated commendable commitment throughout {target_month}. "
            "Punctuality and focus have been consistent, leading to noticeable improvement in subject confidence."
        ),
        "Head Teacher Recommendations": (
            "Approved. Recommended to maintain momentum into next month with continued practice on advanced problem-solving."
        ),
        "Status": "Draft",
        "Teacher Confirmed At": "",
        "Head Teacher Approved At": "",
        "Last Modified": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Associated Report IDs": ", ".join(associated_ids)
    }

    return draft_report


def confirm_monthly_report_teacher(client, report_id, teacher_name, teacher_remarks=None):
    """
    Teacher sign-off action: Sets status to 'Confirmed by Teacher'.
    """
    df_m = get_monthly_reports_data(client)
    if df_m.empty:
        return False, "No monthly reports found."
        
    matches = df_m[df_m["Monthly Report ID"] == report_id]
    if matches.empty:
        return False, f"Report ID '{report_id}' not found."
        
    rep_dict = matches.iloc[0].to_dict()
    rep_dict["Status"] = "Confirmed by Teacher"
    rep_dict["Teacher Confirmed At"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if teacher_remarks:
        rep_dict["Teacher Remarks"] = teacher_remarks
    if teacher_name:
        rep_dict["Teacher Name"] = teacher_name
        
    return save_monthly_report(client, rep_dict)


def approve_monthly_report_head_teacher(client, report_id, head_teacher_name="Head Teacher", recommendations=None):
    """
    Head Teacher sign-off action: Sets status to 'Approved by Head Teacher'.
    """
    df_m = get_monthly_reports_data(client)
    if df_m.empty:
        return False, "No monthly reports found."
        
    matches = df_m[df_m["Monthly Report ID"] == report_id]
    if matches.empty:
        return False, f"Report ID '{report_id}' not found."
        
    rep_dict = matches.iloc[0].to_dict()
    rep_dict["Status"] = "Approved by Head Teacher"
    rep_dict["Head Teacher Approved At"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if recommendations:
        rep_dict["Head Teacher Recommendations"] = recommendations
        
    return save_monthly_report(client, rep_dict)


def generate_monthly_report_html(report_dict):
    """
    Generates a high-end, printable HTML/PDF-ready evaluation document
    styled with Pinnacle Academic Services branding, metrics, signatures, and print CSS.
    """
    st_name = report_dict.get("Student Name", "Student")
    month = report_dict.get("Month", "Monthly")
    subj = report_dict.get("Subject", "Academic Tutoring")
    t_name = report_dict.get("Teacher Name", "Assigned Tutor")
    classes = report_dict.get("Total Classes", "0")
    hours = report_dict.get("Total Hours", "0")
    curriculum = str(report_dict.get("Curriculum Covered", "")).replace("\n", "<br>")
    hw = str(report_dict.get("Homework Rating", "")).replace("\n", "<br>")
    comp = str(report_dict.get("Comprehension & Progress", "")).replace("\n", "<br>")
    t_remarks = str(report_dict.get("Teacher Remarks", "")).replace("\n", "<br>")
    ht_recs = str(report_dict.get("Head Teacher Recommendations", "")).replace("\n", "<br>")
    status = report_dict.get("Status", "Draft")
    t_confirmed = report_dict.get("Teacher Confirmed At", "")
    ht_approved = report_dict.get("Head Teacher Approved At", "")

    status_badge_color = "#10b981" if status == "Approved by Head Teacher" else "#3b82f6" if status == "Confirmed by Teacher" else "#f59e0b"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PAS Academic Evaluation - {st_name} ({month})</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  
  @page {{
    size: A4 portrait;
    margin: 14mm;
  }}
  
  * {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: #f8fafc;
    color: #1e293b;
    margin: 0;
    padding: 24px;
    font-size: 13px;
    line-height: 1.55;
  }}
  
  .container {{
    max-width: 820px;
    margin: 0 auto;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 36px 40px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.06);
  }}
  
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #1e3a8a;
    padding-bottom: 18px;
    margin-bottom: 24px;
  }}
  
  .logo-title h1 {{
    margin: 0;
    font-size: 24px;
    font-weight: 800;
    color: #1e3a8a;
    letter-spacing: -0.5px;
  }}
  
  .logo-title p {{
    margin: 4px 0 0 0;
    font-size: 13px;
    color: #64748b;
    font-weight: 500;
  }}
  
  .status-tag {{
    display: inline-block;
    padding: 6px 14px;
    border-radius: 20px;
    background: {status_badge_color}15;
    color: {status_badge_color};
    font-weight: 700;
    font-size: 12px;
    border: 1px solid {status_badge_color}40;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  
  .meta-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    background: #f1f5f9;
    padding: 16px;
    border-radius: 8px;
    margin-bottom: 26px;
  }}
  
  .meta-item span {{
    display: block;
    font-size: 11px;
    color: #64748b;
    text-transform: uppercase;
    font-weight: 600;
    letter-spacing: 0.4px;
  }}
  
  .meta-item strong {{
    font-size: 14px;
    color: #0f172a;
  }}
  
  .section {{
    margin-bottom: 22px;
  }}
  
  .section-title {{
    font-size: 14px;
    font-weight: 700;
    color: #1e3a8a;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    border-bottom: 1px solid #cbd5e1;
    padding-bottom: 5px;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  
  .content-box {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 14px 16px;
    color: #334155;
  }}
  
  .signatures-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-top: 32px;
    padding-top: 20px;
    border-top: 1px solid #e2e8f0;
  }}
  
  .sig-card {{
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 14px;
    background: #fafafa;
  }}
  
  .sig-card strong {{
    color: #1e3a8a;
    font-size: 13px;
  }}
  
  .footer {{
    margin-top: 28px;
    text-align: center;
    font-size: 11px;
    color: #94a3b8;
    border-top: 1px solid #e2e8f0;
    padding-top: 12px;
  }}

  .print-btn {{
    display: block;
    margin: 0 auto 20px auto;
    padding: 10px 24px;
    background: #1e3a8a;
    color: white;
    font-weight: 600;
    font-size: 14px;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    box-shadow: 0 2px 6px rgba(30, 58, 138, 0.3);
  }}

  @media print {{
    body {{
      background: white;
      padding: 0;
    }}
    .container {{
      border: none;
      box-shadow: none;
      padding: 0;
      max-width: 100%;
    }}
    .print-btn {{
      display: none !important;
    }}
  }}
</style>
</head>
<body>

<button class="print-btn" onclick="window.print()">🖨️ Print / Save as PDF for Parent</button>

<div class="container">
  <div class="header">
    <div class="logo-title">
      <h1>Pinnacle Academic Services (PAS)</h1>
      <p>Monthly Academic Evaluation & Student Progress Report</p>
    </div>
    <div>
      <span class="status-tag">{status}</span>
    </div>
  </div>

  <div class="meta-grid">
    <div class="meta-item">
      <span>Student Name</span>
      <strong>{st_name}</strong>
    </div>
    <div class="meta-item">
      <span>Subject(s)</span>
      <strong>{subj}</strong>
    </div>
    <div class="meta-item">
      <span>Evaluation Period</span>
      <strong>{month}</strong>
    </div>
    <div class="meta-item">
      <span>Classes / Hours</span>
      <strong>{classes} Classes ({hours}h)</strong>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📚 1. Curriculum & Topics Covered</div>
    <div class="content-box">
      {curriculum}
    </div>
  </div>

  <div class="section">
    <div class="section-title">📝 2. Homework & Independent Practice</div>
    <div class="content-box">
      {hw}
    </div>
  </div>

  <div class="section">
    <div class="section-title">🎯 3. Concept Comprehension & Engagement</div>
    <div class="content-box">
      {comp}
    </div>
  </div>

  <div class="section">
    <div class="section-title">👨‍🏫 4. Teacher's Evaluation & Remarks</div>
    <div class="content-box">
      {t_remarks}
    </div>
  </div>

  <div class="section">
    <div class="section-title">👑 5. Head Teacher's Quality Seal & Recommendations</div>
    <div class="content-box">
      {ht_recs}
    </div>
  </div>

  <div class="signatures-grid">
    <div class="sig-card">
      <div style="font-size:11px; color:#64748b; text-transform:uppercase;">Confirmed by Assigned Tutor</div>
      <div style="margin-top:6px; font-weight:700; color:#0f172a;">{t_name}</div>
      <div style="font-size:11px; color:#64748b; margin-top:2px;">Timestamp: {t_confirmed or 'Awaiting Teacher Sign-off'}</div>
    </div>
    <div class="sig-card">
      <div style="font-size:11px; color:#64748b; text-transform:uppercase;">Endorsed by Quality Assurance Head</div>
      <div style="margin-top:6px; font-weight:700; color:#0f172a;">Head Teacher (PAS Academic Team)</div>
      <div style="font-size:11px; color:#64748b; margin-top:2px;">Timestamp: {ht_approved or 'Awaiting Head Teacher Approval'}</div>
    </div>
  </div>

  <div class="footer">
    Pinnacle Academic Services • Dedicated to Academic Excellence • Questions or inquiries: info@pinnacleacademicservices.com
  </div>
</div>

</body>
</html>"""
    return html




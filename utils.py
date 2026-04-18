import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
import datetime
import json
import re
import functools


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
    Decorator to retry API calls on Quota Exceeded error.
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
                if "429" in err_str or "quota" in err_str:
                    if i < retries - 1:
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
            # Split by comma and normalize
            assigned_list = [a.strip().lower() for a in assigned_raw.split(',') if a.strip()]
            
            for s in assigned_list:
                if s not in student_teacher_map:
                    student_teacher_map[s] = []
                student_teacher_map[s].append(t_name)
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
        
        # Regex: Subject \((Day) (Start)( - End)?\)
        # Group 1: Subject
        # Group 2: Day
        # Group 3: Start Time
        # Group 4: End Time (Optional)
        pattern = r"^(.*?)\s*\(\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2}:\d{2}\s*[AP]M)(?:\s*-\s*(\d{1,2}:\d{2}\s*[AP]M))?\s*\)$"
        match = re.search(pattern, part, re.IGNORECASE)
        
        if match:
            subj = match.group(1).strip()
            day_short = match.group(2).title()
            start_str = match.group(3).upper()
            end_str = match.group(4).upper() if match.group(4) else None
            
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
                    # Use existing parse_schedule_string which returns a dict
                    # If it returns distinct days but misses times, it defaults to 9-5.
                    # We might want strict validation here too?
                    # For now, let's just check if it parses at all.
                    parsed = parse_schedule_string(sched)
                    # Simple check: if sched has content but parsed is empty?
                    if not parsed and len(sched) > 10:
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
                # MATCH TEACHER using Normalized Name
                s_key = s_name.strip().lower()
                potential_teachers = student_teacher_map.get(s_key, [])
                
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
    SENDER_PASSWORD = st.secrets.get("EMAIL_PASSWORD", "Lanadel040924") 
    BASE_APP_URL = st.secrets.get("APP_URL", "https://pas-dashboard-gcvkbpip4geh7cchnpgqya.streamlit.app")
except FileNotFoundError:
    # If no secrets.toml exists (local dev), use defaults
    SENDER_EMAIL = "Pinnacleassistance1@gmail.com"
    SENDER_PASSWORD = "Lanadel040924"
    BASE_APP_URL = "http://localhost:8501" # Default to localhost if no secrets
except Exception:
    # Catch StreamlitSecretNotFoundError (which might be ImportError or other)
    SENDER_EMAIL = "Pinnacleassistance1@gmail.com"
    SENDER_PASSWORD = "Lanadel040924"
    BASE_APP_URL = "http://localhost:8501"

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

def schedule_class(client, teacher_name, student_name, subject, time_str, meeting_link):
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            # Ensure Sessions tab exists
            get_sessions_data(client) 
            
            ws = sheet.worksheet("Sessions")
            session_id = str(uuid.uuid4())
            
            # Generate Code (Still needed for manual backup?) -> Kept as fallback
            code = str(random.randint(100000, 999999))
            
            # 1. Fetch Emails
            t_email = ""
            df_t = get_teacher_data(client)
            if not df_t.empty and "Teacher Name" in df_t.columns and "Email" in df_t.columns:
                matches = df_t[df_t["Teacher Name"] == teacher_name]
                if not matches.empty: t_email = matches.iloc[0]["Email"]

            s_email = ""
            df_s = get_students_data(client)
            if not df_s.empty and "Student Name" in df_s.columns and "Email" in df_s.columns:
                matches = df_s[df_s["Student Name"] == student_name]
                if not matches.empty: s_email = matches.iloc[0]["Email"]
            
            if not t_email or not s_email:
                 return False, f"Missing Email! Teacher: {t_email}, Student: {s_email}"

            # 2. Add Row
            ws.append_row([
                session_id, teacher_name, student_name, subject, str(time_str), 
                meeting_link, "Scheduled", code, "", "", ""
            ])
            
            # 3. Send Email with Magic Link
            email_success, email_msg = send_email_invite(t_email, s_email, subject, time_str, session_id, meeting_link)
            
            if email_success:
                get_sessions_data.clear()
                return True, "Invites Sent Successfully!", session_id
            else:
                get_sessions_data.clear()
                return True, f"Class Scheduled but Email Failed: {email_msg}", session_id
            
        except Exception as e:
            st.error(f"Error scheduling class: {e}")
            return False, str(e), None
    return False, "No Sheet", None

def clock_in_by_id(client, session_id, role):
    """
    Magic Link Clock-in using Session ID.
    Returns: Success (Bool), Message (Str), Meeting Link (Str)
    """
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            ws = sheet.worksheet("Sessions")
            cell = ws.find(session_id)
            if cell:
                row = cell.row
                
                # Verify Status
                status = ws.cell(row, 7).value # Col 7: Status
                if status not in ["Scheduled", "In-Progress"]:
                     return False, "Class already completed.", ""

                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                meeting_link = ws.cell(row, 6).value # Col 6: Link
                
                # Update Time
                if role == "Teacher":
                    ws.update_cell(row, 9, now) # Col 9: Teacher Join
                elif role == "Student":
                    ws.update_cell(row, 10, now) # Col 10: Student Join
                
                # Update Status to In-Progress (Session Active)
                ws.update_cell(row, 7, "In-Progress")

                get_sessions_data.clear()
                return True, "Clocked In Successfully!", meeting_link
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


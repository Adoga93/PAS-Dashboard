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

def get_billing_data(client):
    """
    Fetches billing data. Returns a DataFrame.
    """
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
            worksheet = sheet.worksheet("Billing")
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
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
                    0,  # Current Balance (Starts at 0)
                    ""  # Last Bill Date
                ]
                ws_billing.append_row(row_billing)
            
            return True
        except Exception as e:
            st.error(f"Error saving student: {e}")
            return False
    return True

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
            
            balance = 0
            if recalculate:
                # Calculate based on history
                balance = calculate_historical_balance(client, student_name, billing_data.get("Rate"), billing_data.get("Billing Type"))

            if cell:
                # Update existing row
                row_num = cell.row
                # Update cols 2, 3, 4, 5, 6 (Billing Type, Rate, Currency, Terms, Balance)
                # Note: This is a bit manual, using update_cell or update.
                # Only update balance if recalculate is True, otherwise keep existing? 
                # For simplicity, if Recalculate is False, we keep existing balance.
                
                if not recalculate:
                     # Fetch existing balance
                     existing_balance = ws_billing.cell(row_num, 6).value
                     balance = existing_balance

                ws_billing.update(f"B{row_num}:F{row_num}", [[
                    billing_data.get("Billing Type"),
                     billing_data.get("Rate"),
                     billing_data.get("Currency"),
                     billing_data.get("Payment Terms"),
                     balance
                ]])
            else:
                # Append new
                row_billing = [
                    student_name,
                    billing_data.get("Billing Type"),
                    billing_data.get("Rate"),
                    billing_data.get("Currency"),
                    billing_data.get("Payment Terms"),
                    balance,
                    ""
                ]
                ws_billing.append_row(row_billing)
            
            return True, f"Billing updated. Balance: {balance}"
        except Exception as e:
            return False, str(e)
    return False, "No Sheet"

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
            return True
        except Exception as e:
             st.error(f"Error saving teacher: {e}")
             return False
    return True

def get_teacher_data(client):
    sheet = get_sheet_by_id(client)
    if sheet:
        try:
             worksheet = sheet.worksheet("Teachers")
             data = worksheet.get_all_records()
             return pd.DataFrame(data)
        except Exception:
             return pd.DataFrame()
    return pd.DataFrame()

def calculate_teacher_pay(client, teacher_name, percentage_share):
    """
    Calculates pay based on: Sum(Student Rate for each class) * Percentage Share.
    Returns: count, total_revenue, teacher_pay
    """
    try:
        sheet = get_sheet_by_id(client)
        ws_reviews = sheet.worksheet("Reviews")
        # Review structure: Timestamp, Teacher Name, Student Name, Review
        # Index: 0, 1, 2, 3
        
        qt_reviews = ws_reviews.get_all_values() # Get strictly values, less API calls thn col_values
        # Headers are usually row 1, skip if needed but safe to iterate
        
        # 1. Filter reviews for this teacher
        teacher_reviews = [row for row in qt_reviews if len(row) > 2 and row[1] == teacher_name]
        count = len(teacher_reviews)
        
        if count == 0:
            return 0, 0.0, 0.0

        # 2. Get Billing Data for Lookups
        df_billing = get_billing_data(client)
        if df_billing.empty:
            return count, 0.0, 0.0
            
        # Create a lookup dict: Student Name -> Rate
        # Assuming "Rate" is column 2 (index), "Student Name" is 0
        # Check col names first to be safe
        rate_map = {}
        for index, row in df_billing.iterrows():
             try:
                 s_name = row["Student Name"]
                 rate = float(str(row["Rate"]).replace(',', '').replace('$', '').replace('NGN', '').strip())
                 rate_map[s_name] = rate
             except:
                 continue
        
        total_revenue = 0.0
        
        # 3. Sum up revenue from each class
        for rev in teacher_reviews:
            student_taught = rev[2] # Column C
            # Ensure exact match or approximate? Exact for now.
            if student_taught in rate_map:
                total_revenue += rate_map[student_taught]
            else:
                # Fallback: Maybe log missing rates?
                pass
        
        teacher_pay = total_revenue * (percentage_share / 100.0)
        return count, total_revenue, teacher_pay

    except Exception as e:
        print(f"Error calc teacher pay: {e}")
        return 0, 0.0, 0.0

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

# --- SESSION MANAGEMENT (PHASE 2) ---
import uuid
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Email Configuration
# Try to get from secrets, else use provided fallback
SENDER_EMAIL = st.secrets.get("EMAIL_USER", "Pinnacleassistance1@gmail.com")
SENDER_PASSWORD = st.secrets.get("EMAIL_PASSWORD", "Lanadel040924") 

# App URL (Critical for Magic Links)
# In production, this must be set in secrets to the actual URL (e.g., "https://pas-tutors.streamlit.app")
# User provided: https://pas-dashboard-gcvkbpip4geh7cchnpgqya.streamlit.app/
BASE_APP_URL = st.secrets.get("APP_URL", "https://pas-dashboard-gcvkbpip4geh7cchnpgqya.streamlit.app")

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

def get_sessions_data(client):
    sheet = get_sheet_by_id(client)
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
                return True, "Invites Sent Successfully!", session_id
            else:
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
                
                return True, "Student updated successfully!"
            else:
                return False, "Student not found."
        except Exception as e:
            return False, str(e)
    return False, "No Sheet"

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
                return True, "Teacher updated successfully!"
            else:
                return False, "Teacher not found."
        except Exception as e:
            return False, str(e)
    return False, "No Sheet"


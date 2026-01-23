import streamlit as st
import pandas as pd
import plotly.express as px
import utils


st.set_page_config(page_title="PAS Tutors Dashboard", layout="wide")

# --- DATA LOADER ---
# Load client once (cache resource if needed, but simple for now)
client = utils.get_google_sheet_client()

if not client:
    st.warning("⚠️ Running in Mock Mode. `credentials.json` not found or invalid.")

# --- SIDEBAR ---
st.sidebar.title("PAS Tutors")
st.sidebar.markdown("---")
tab = st.sidebar.radio("Navigate to", ["Student Tab", "Teacher Tab", "Registration", "Admin Dashboard"])

# --- STUDENT TAB ---
if tab == "Student Tab":
    st.header("🎓 Student Progress & Payments")
    
    df_students = utils.get_students_data(client)
    
    if not df_students.empty:
        # Search filter
        search_query = st.text_input("🔍 Search Student", "")
        if search_query:
            df_students = df_students[df_students["Student Name"].str.contains(search_query, case=False, na=False)]

        # Normalize Payment Status (Case-insensitive + Strip Whitespace)
        if "Payment Status" in df_students.columns:
            df_students["Payment Status"] = (
                df_students["Payment Status"]
                .astype(str)
                .str.strip()
                .str.title()  # Converts 'paid' -> 'Paid', 'PAID' -> 'Paid'
            )

        # Display Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Students", len(df_students))
        
        # Count based on normalized values
        paid_count = len(df_students[df_students["Payment Status"] == "Paid"])
        col2.metric("Paid", paid_count)
        
        pending_count = len(df_students[df_students["Payment Status"] == "Pending"])
        col3.metric("Pending", pending_count)

        st.markdown("### Student List")
        # Format the dataframe? Streamlit does a good job by default.
        # Maybe color code payment status?
        def highlight_status(val):
            color = 'green' if val == 'Paid' else 'red' if val == 'Overdue' else 'orange'
            return f'color: {color}'

        # Prepare dataframe for display (Add links)
        df_display = df_students.copy()
        
        if "Email" in df_display.columns:
            df_display["Email_Link"] = "mailto:" + df_display["Email"].astype(str)
        if "Phone" in df_display.columns:
            df_display["Phone_Link"] = "tel:" + df_display["Phone"].astype(str)

        # Configure columns
        column_config = {
            "Email_Link": st.column_config.LinkColumn("Email", display_text=r"mailto:(.*)"),
            "Phone_Link": st.column_config.LinkColumn("Phone", display_text=r"tel:(.*)"),
            "Email": None, # Hide original
            "Phone": None  # Hide original
        }

        # Apply style if column exists
        if "Payment Status" in df_students.columns:
            st.dataframe(
                df_display.style.applymap(highlight_status, subset=['Payment Status']),
                use_container_width=True,
                hide_index=True,
                column_config=column_config
            )
        else:
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config=column_config
            )
    else:
        st.info("No student data available yet.")

# --- TEACHER TAB ---
elif tab == "Teacher Tab":
    st.header("🍎 Teacher Check-in")
    st.markdown("Please submit your class review below.")
    
    with st.form("checkin_form"):
        teacher_name = st.text_input("Your Name")
        
        # Fetch student list
        df_students = utils.get_students_data(client)
        student_list = df_students["Student Name"].tolist() if not df_students.empty else []
        
        if not student_list:
            st.warning("Please register a student first.")
            student_name = None # Or disable the field
        else:
            student_name = st.selectbox("Student Name", student_list)
            
        review_comment = st.text_area("Class Review / Comments")
        
        submitted = st.form_submit_button("Submit Check-in")
        
        if submitted:
            if not student_name:
                st.error("Please select a student.")
            elif teacher_name and review_comment:
                success = utils.add_review(client, teacher_name, student_name, review_comment)
                if success:
                    st.success(f"✅ Check-in submitted for {student_name}!")
                else:
                    st.error("❌ Failed to submit review.")
            else:
                st.warning("Please fill in all fields.")

# --- REGISTRATION TAB ---
elif tab == "Registration":
    st.header("📝 Registration")
    
    # Sidebar Toggle within the Registration page context or just use main page
    # The user asked for: "Sidebar Registration: Add a 'Registration' section in the sidebar with a toggle to choose between 'Register Student' or 'Register Teacher'."
    # Since I put "Registration" as a main nav item, I'll put the toggle here on the main page or in the sidebar.
    # To strictly follow "Sidebar Registration... with a toggle", let's put the toggle in the sidebar ONLY when Registration is active.
    
    reg_type = st.sidebar.radio("Registration Type", ["Register Student", "Register Teacher"])
    
    if reg_type == "Register Student":
        st.subheader("New Student Registration")
        
        # Initialize session state for subject rows
        if "reg_subject_rows" not in st.session_state:
            st.session_state.reg_subject_rows = 1

        name = st.text_input("Full Name")
        email = st.text_input("Email")
        phone = st.text_input("Phone Number")
        
        st.markdown("### Subjects & Class Times")
        
        subject_options = ["Maths", "English", "Physics", "Chemistry", "Biology", "Science", "History", "Geography", "Other"]
        day_options = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        all_subjects_data = []
        
        for i in range(st.session_state.reg_subject_rows):
            col1, col2, col3 = st.columns(3)
            with col1:
                sub = st.selectbox(f"Subject {i+1}", subject_options, key=f"sub_{i}")
            with col2:
                day = st.selectbox(f"Day {i+1}", day_options, key=f"day_{i}")
            with col3:
                time = st.time_input(f"Time {i+1}", key=f"time_{i}")
            
            all_subjects_data.append({"Subject": sub, "Day": day, "Time": time})

        def add_subject_row():
            st.session_state.reg_subject_rows += 1
        
        st.button("+ Add Another Subject", on_click=add_subject_row)
        
        st.markdown("---")
        
        if st.button("Register Student"):
            if name:
                # Format strings
                subject_list = [entry['Subject'] for entry in all_subjects_data]
                subjects_str = ", ".join(subject_list)
                
                class_times_parts = []
                for entry in all_subjects_data:
                    t_str = entry['Time'].strftime("%I:%M %p")
                    class_times_parts.append(f"{entry['Subject']} ({entry['Day'][:3]} {t_str})")
                
                class_times_str = ", ".join(class_times_parts)
                
                student_data = {
                    "Name": name,
                    "Email": email,
                    "Phone": phone,
                    "Class Times": class_times_str,
                    "Subjects": subjects_str
                }
                
                if utils.add_student(client, student_data):
                    st.success(f"✅ Student {name} registered successfully!")
                else:
                    st.error("❌ Failed to register student.")
            else:
                st.warning("Name is required.")

    elif reg_type == "Register Teacher":
        st.subheader("New Teacher Registration")
        
        name = st.text_input("Full Name")
        email = st.text_input("Email")
        phone = st.text_input("Phone Number")
        expertise = st.text_input("Expertise (e.g. Math, Physics)")
        
        # Fetch student list for dropdown
        df_students_reg = utils.get_students_data(client)
        student_options = df_students_reg["Student Name"].tolist() if not df_students_reg.empty else []
        
        assigned_students_list = st.multiselect("Assigned Students", student_options)
        assigned_students = ", ".join(assigned_students_list)
        
        st.markdown("### Availability")
        st.markdown("Select days and times you are available.")
        
        days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        availability_data = {}
        
        for day in days_of_week:
            col1, col2, col3 = st.columns([1, 2, 2])
            with col1:
                is_checked = st.checkbox(day)
            
            if is_checked:
                with col2:
                    start_time = st.time_input(f"Start Time ({day})", key=f"start_{day}")
                with col3:
                    end_time = st.time_input(f"End Time ({day})", key=f"end_{day}")
                
                # Format: "Day (Start - End)"
                t_start = start_time.strftime("%I:%M %p")
                t_end = end_time.strftime("%I:%M %p")
                availability_data[day] = f"{t_start} - {t_end}"
        
        st.markdown("---")
        
        if st.button("Register Teacher"):
            if name:
                # Format availability string
                # e.g. "Monday (09:00 AM - 05:00 PM), Tuesday (...)"
                avail_parts = []
                for day in days_of_week: # Maintain order
                    if day in availability_data:
                        avail_parts.append(f"{day} ({availability_data[day]})")
                
                availability_str = ", ".join(avail_parts) if avail_parts else "Not Specified"
            
                teacher_data = {
                    "Name": name,
                    "Email": email,
                    "Phone": phone,
                    "Expertise": expertise,
                    "Assigned Students": assigned_students,
                    "Availability": availability_str
                }
                
                if utils.add_teacher(client, teacher_data):
                    st.success(f"✅ Teacher {name} registered successfully!")
                else:
                    st.error("❌ Failed to register teacher.")
            else:
                st.warning("Name is required.")

# --- ADMIN DASHBOARD ---
elif tab == "Admin Dashboard":
    st.header("📊 Admin Dashboard")
    
    df_students = utils.get_students_data(client)
    
    if not df_students.empty:
        # Row 1: Charts
        st.subheader("Financial Overview")
        if "Payment Status" in df_students.columns:
            payment_counts = df_students["Payment Status"].value_counts().reset_index()
            payment_counts.columns = ["Status", "Count"]
            
            fig = px.pie(payment_counts, values='Count', names='Status', 
                         title='Payment Status Distribution',
                         color='Status',
                         color_discrete_map={'Paid':'green', 'Pending':'orange', 'Overdue':'red'})
            st.plotly_chart(fig, use_container_width=True)
        
        # Row 2: Action Items
        st.subheader("⚠️ Action Items")
        # Identify "Action Items" (e.g., Overdue payments or Low Attendance)
        
        # Filter for Overdue
        overdue_students = df_students[df_students["Payment Status"] == "Overdue"]
        
        # Filter for Low Attendance (assuming format "90%" -> need to parse)
        # Simple parsing logic
        def parse_attendance(val):
            try:
                return int(str(val).replace('%', ''))
            except:
                return 0
        
        if "Attendance" in df_students.columns:
            df_students["Attendance_Num"] = df_students["Attendance"].apply(parse_attendance)
            low_attendance = df_students[df_students["Attendance_Num"] < 50]
        else:
            low_attendance = pd.DataFrame()

        col1, col2 = st.columns(2)
        
        with col1:
            st.warning("🔴 Overdue Payments")
            if not overdue_students.empty:
                st.table(overdue_students[["Student Name", "Payment Status"]])
            else:
                st.write("No overdue payments! 🎉")
                
        with col2:
            st.warning("📉 Low Attendance (< 50%)")
            if not low_attendance.empty:
                st.table(low_attendance[["Student Name", "Attendance"]])
            else:
                st.write("All attendance is good! 🌟")
                
        # Row 3: Full Data View (Optional)
        with st.expander("View All Raw Data"):
            st.dataframe(df_students)
            
    else:
        st.info("No data to display.")

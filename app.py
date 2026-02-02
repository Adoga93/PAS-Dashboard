import streamlit as st
import pandas as pd
import plotly.express as px
import utils
import time
import datetime


st.set_page_config(page_title="PAS Tutors Dashboard", layout="wide")

# --- DATA LOADER ---
# Load client once (cache resource if needed, but simple for now)
client = utils.get_google_sheet_client()



if not client:
    st.warning("⚠️ Running in Mock Mode. `credentials.json` not found or invalid.")

# --- MAGIC LINK HANDLER (AUTO-CLOCK-IN) ---
# Check query params for action=clock_in
query_params = st.query_params
if "action" in query_params and query_params["action"] == "clock_in":
    session_id = query_params.get("session_id")
    role = query_params.get("role")
    
    st.title("🚀 Join Class")
    
    if session_id and role:
        # Auto Clock-in
        # For security in a real app, we'd verify a signature or token.
        # Here we trust the link for simplicity as requested.
        
        # We need to map role -> Name. But name isn't in link?
        # Correction: clock_in needs Code or ID?
        # utils.clock_in uses CODE. But we have ID.
        # We need a new util: clock_in_by_id(session_id, role)
        
        success, msg, meeting_link = utils.clock_in_by_id(client, session_id, role)
        
        if success:
            st.balloons() # Special auto-login celebration
            st.success(f"✅ Welcome {role}! You are Clocked In.")
            st.markdown(f"### [👉 CLICK TO JOIN MEETING]({meeting_link})")
            st.caption("You may close this tab after joining.")
        else:
            st.error(f"❌ Error: {msg}")
    else:
        st.error("Invalid Link.")
    
    st.stop() # Stop rendering the rest of the app

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
        
        # Calculate Total Outstanding Balance from Billing Tab
        df_billing = utils.get_billing_data(client)
        total_outstanding = 0.0
        if not df_billing.empty and "Current Balance" in df_billing.columns:
            # Clean and sum
            def clean_balance(val):
                try:
                    return float(str(val).replace(',', '').replace('$', '').replace('NGN', '').strip())
                except:
                    return 0.0
            total_outstanding = df_billing["Current Balance"].apply(clean_balance).sum()
        
        col3.metric("Total Outstanding Balance", f"NGN {total_outstanding:,.2f}")

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



    st.markdown("---")
    st.subheader("✅ Class Portal")
    with st.expander("Clock In (Students & Teachers)", expanded=True):
         st.info("Check your email for the Class Code!")
         u_code = st.text_input("Enter Attendance Code", key="univ_code")
         # We need to ask if they are Teacher or Student to know where to log time
         # OR simply ask for Name and infer? 
         # Let's ask Role for explicit clarity.
         u_role = st.radio("I am a:", ["Student", "Teacher"], horizontal=True)
         u_name = st.text_input("Your Name", key="univ_name")
         
         if st.button("Clock In"):
             if u_code and u_name:
                 success, msg = utils.clock_in(client, u_code, u_name, u_role)
                 if success:
                     st.balloons()
                     st.success(f"✅ {msg}")
                 else:
                     st.error(f"❌ {msg}")
             else:
                 st.warning("Please enter code and name.")

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

    st.markdown("---")
    st.subheader("🏫 My Classroom")
    
    if teacher_name:
        df_sessions = utils.get_sessions_data(client)
        if not df_sessions.empty:
            # Filter for this teacher and active/scheduled classes
            # Columns: Session ID, Teacher Name, Student Name, Subject, Scheduled Time, Status, Attendance Code
            my_classes = df_sessions[
                (df_sessions["Teacher Name"] == teacher_name) & 
                (df_sessions["Status"].isin(["Scheduled", "In-Progress"]))
            ]
            
            if not my_classes.empty:
                st.write(f"You have {len(my_classes)} upcoming/active classes.")
                
                for index, row in my_classes.iterrows():
                    with st.container():
                        st.info(f"**{row['Subject']}** with {row['Student Name']} @ {row['Scheduled Time']}")
                        status = row['Status']
                        s_id = row['Session ID']
                        
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.write(f"Status: **{status}**")
                        
                        with c2:
                            if status == "Scheduled" or status == "In-Progress":
                                st.markdown(f"### 🔑 CODE: `{row['Attendance Code']}`")
                                if str(row.get("Meeting Link", "")):
                                     st.markdown(f"[Join Meeting]({row['Meeting Link']})")
                        
                        with c3:
                            if status == "In-Progress" or status == "Scheduled":
                                if st.button(f"🛑 End Class", key=f"end_{s_id}"):
                                    if utils.end_class_v2(client, s_id):
                                        st.success("Class Ended & Logged!")
                                        st.rerun()
                                    else:
                                        st.error("Error ending class.")
                        st.markdown("---")
            else:
                st.info("No scheduled classes found. Ask Admin to schedule one.")
    else:
        st.warning("Enter your name above to see your classes.")

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
        
        subject_options = [
            "Maths", "English", "Physics", "Chemistry", "Biology", "Science", "History", "Geography",
            "Literacy", "Reading", "Creative writing", "Spelling", "Verbal reasoning", "Quantitative reasoning",
            "Phonics", "Social Studies", "Art", "Music", "Computer Science",
            "Other"
        ]
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
        st.subheader("Billing Profile")
        
        bill_type = st.selectbox("Billing Type", ["Per Hour", "Per Class", "Monthly Fixed"])
        rate_amount = st.number_input("Rate / Amount", min_value=0.0, step=500.0)
        
        # Currency Toggle
        currency_options = ["NGN", "USD"]
        currency = st.radio("Currency", currency_options, horizontal=True)
        
        payment_terms = st.selectbox("Payment Terms", ["Pre-paid", "Post-paid"])
        
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
                
                if utils.add_student(client, student_data, billing_data={
                    "Billing Type": bill_type,
                    "Rate": rate_amount,
                    "Currency": currency,
                    "Payment Terms": payment_terms
                }):
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
        # Use the same subject options for expertise, or a similar list
        subject_options = [
            "Maths", "English", "Physics", "Chemistry", "Biology", "Science", "History", "Geography",
            "Literacy", "Reading", "Creative writing", "Spelling", "Verbal reasoning", "Quantitative reasoning",
            "Phonics", "Social Studies", "Art", "Music", "Computer Science",
            "Other"
        ]
        expertise_list = st.multiselect("Expertise (Subjects)", subject_options)
        expertise = ", ".join(expertise_list)
        
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
    
    # --- MASTER SCHEDULE PREVIEW ---
    st.subheader("📅 Master Class Schedule")
    
    # Date/Day Selector
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    today_str = datetime.datetime.now().strftime("%A")
    # Default to today if valid, else Monday
    default_idx = days_of_week.index(today_str) if today_str in days_of_week else 0
    
    col_day, col_empty = st.columns([1, 2])
    with col_day:
        selected_day_view = st.selectbox("Select Day", days_of_week, index=default_idx)
    
    # Fetch Teachers to build schedule
    df_teachers_sched = utils.get_teacher_data(client)
    
    daily_agenda = []
    
    if not df_teachers_sched.empty:
        for idx, t_row in df_teachers_sched.iterrows():
            t_name = t_row.get("Teacher Name", "Unknown")
            t_sched_str = t_row.get("Class Schedule", "")
            t_expertise = t_row.get("Subject Expertise", "")
            t_students = t_row.get("Assigned Students", "")
            
            # Parse
            parsed = utils.parse_schedule_string(t_sched_str)
            
            if selected_day_view in parsed:
                start_t, end_t = parsed[selected_day_view]
                # Convert to string for display, but keep object for sorting if needed? 
                # Let's just store sortable string or obj
                
                daily_agenda.append({
                    "Time": f"{start_t.strftime('%I:%M %p')} - {end_t.strftime('%I:%M %p')}",
                    "Teacher": t_name,
                    "Subject/Expertise": t_expertise,
                    "Assigned Students": t_students,
                    "_sort_key": start_t # Hidden key for sorting
                })
    
    if daily_agenda:
        # Sort by start time
        daily_agenda.sort(key=lambda x: x["_sort_key"])
        
        # Remove sort key before display
        for item in daily_agenda:
            del item["_sort_key"]
            
        df_agenda = pd.DataFrame(daily_agenda)
        st.dataframe(df_agenda, use_container_width=True, hide_index=True)
    else:
        st.info(f"No recurring classes scheduled for {selected_day_view}.")
        
    st.markdown("---")

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
                
                st.write("All attendance is good! 🌟")
                
        # Row 3: Edit Records (New)
        st.subheader("✏️ Edit Records")
        with st.expander("Update Student / Teacher Details"):
            et1, et2 = st.tabs(["Edit Student", "Edit Teacher"])
            
            with et1:
                st.caption("Select a student to update their profile.")
                s_list_edit = df_students["Student Name"].tolist() if not df_students.empty else []
                sel_s_edit = st.selectbox("Select Student", s_list_edit, key="edit_s_sel")
                
                # Standard Subject List
                standard_subjects = [
                    "Maths", "English", "Physics", "Chemistry", "Biology", "Science", 
                    "History", "Geography", "Literacy", "Computer Science", "Art", "Music", "Other"
                ]
                
                if sel_s_edit and not df_students.empty and "Student Name" in df_students.columns:
                    # Get current data - Find row where Student Name matches
                    curr_s = df_students[df_students["Student Name"] == sel_s_edit].iloc[0]
                    
                    with st.form("edit_s_form"):
                        # Use .get with defaults. keys match exact sheet headers usually.
                        
                        es_name = st.text_input("Name", curr_s.get("Student Name", ""), help="Changing name will update Billing profile too.")
                        es_email = st.text_input("Email", curr_s.get("Email", "")) # or "Email Address"?
                        es_phone = st.text_input("Phone", curr_s.get("Phone", "")) # or "Phone Number"?
                        
                        # Subjects Multiselect
                        curr_subs_str = str(curr_s.get("Subjects", ""))
                        curr_subs_list = [x.strip() for x in curr_subs_str.split(",")] if curr_subs_str else []
                        # Ensure defaults are in options or add custom ones? 
                        # For simplicity, we filter to defaults.
                        valid_subs = [x for x in curr_subs_list if x in standard_subjects]
                        # If meaningful data is lost, we might need to handle "Other" better, but usually okay.
                        
                        es_subj_list = st.multiselect("Subjects", standard_subjects, default=valid_subs)
                        es_subj = ", ".join(es_subj_list)
                        
                        es_times = st.text_input("Class Times", curr_s.get("Class Times", ""))
                        
                        if st.form_submit_button("Update Student"):
                            success, msg = utils.update_student(client, sel_s_edit, {
                                "Name": es_name,
                                "Email": es_email,
                                "Phone": es_phone,
                                "Subjects": es_subj,
                                "Class Times": es_times
                            })
                            if success: 
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else: 
                                st.error(msg)

            with et2:
                st.caption("Select a teacher to update their profile.")
                df_teachers_edit = utils.get_teacher_data(client)
                t_list_edit = df_teachers_edit["Teacher Name"].tolist() if not df_teachers_edit.empty and "Teacher Name" in df_teachers_edit.columns else []
                sel_t_edit = st.selectbox("Select Teacher", t_list_edit, key="edit_t_sel")
                
                if sel_t_edit and not df_teachers_edit.empty:
                    curr_t = df_teachers_edit[df_teachers_edit["Teacher Name"] == sel_t_edit].iloc[0]
                    
                    with st.form("edit_t_form"):
                        et_name = st.text_input("Name", curr_t.get("Teacher Name", ""))
                        et_email = st.text_input("Email", curr_t.get("Email", ""))
                        et_phone = st.text_input("Phone", curr_t.get("Phone Number", ""))
                        
                        # Expertise Multiselect
                        curr_exp_str = str(curr_t.get("Subject Expertise", ""))
                        curr_exp_list = [x.strip() for x in curr_exp_str.split(",")] if curr_exp_str else []
                        valid_exp = [x for x in curr_exp_list if x in standard_subjects]
                        
                        et_exp_list = st.multiselect("Expertise", standard_subjects, default=valid_exp)
                        et_exp = ", ".join(et_exp_list)
                        
                        # Assigned Students Multiselect (CRITICAL REQUEST)
                        # We use the full student list 's_list_edit' from previous tab scope? 
                        # Need to re-fetch or use df_students which is available in parent scope.
                        # df_students is loaded at top of Admin Dashboard.
                        valid_students_list = df_students["Student Name"].tolist() if not df_students.empty and "Student Name" in df_students.columns else []
                        
                        curr_assign_str = str(curr_t.get("Assigned Students", ""))
                        curr_assign_list = [x.strip() for x in curr_assign_str.split(",")] if curr_assign_str else []
                        
                        # Filter to ensure default values exist in options
                        valid_defaults = [x for x in curr_assign_list if x in valid_students_list]
                        
                        et_assign_list = st.multiselect("Assigned Students", valid_students_list, default=valid_defaults)
                        et_assign = ", ".join(et_assign_list)
                        
                        st.markdown("**Class Schedule (Availability)**")
                        # Structured Schedule Input
                        days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                        curr_sched_str = curr_t.get("Class Schedule", "")
                        parsed_sched = utils.parse_schedule_string(curr_sched_str)
                        
                        et_avail_data = {}
                        
                        for day in days_of_week:
                            is_active = day in parsed_sched
                            col1, col2, col3 = st.columns([1.5, 2, 2])
                            with col1:
                                is_checked = st.checkbox(day, value=is_active, key=f"et_d_{day}")
                            
                            if is_checked:
                                # Default times or parsed times
                                def_start, def_end = parsed_sched.get(day, (datetime.time(9,0), datetime.time(17,0)))
                                
                                with col2:
                                    start_time = st.time_input(f"Start ({day})", value=def_start, key=f"et_s_{day}")
                                with col3:
                                    end_time = st.time_input(f"End ({day})", value=def_end, key=f"et_e_{day}")
                                
                                t_start = start_time.strftime("%I:%M %p")
                                t_end = end_time.strftime("%I:%M %p")
                                et_avail_data[day] = f"{t_start} - {t_end}"

                        if st.form_submit_button("Update Teacher"):
                            # Reconstruct schedule string
                            avail_parts = []
                            for day in days_of_week: 
                                if day in et_avail_data:
                                    avail_parts.append(f"{day} ({et_avail_data[day]})")
                            et_sched_final = ", ".join(avail_parts) if avail_parts else "Not Specified"
                            
                            success, msg = utils.update_teacher(client, sel_t_edit, {
                                "Name": et_name,
                                "Email": et_email,
                                "Phone": et_phone,
                                "Expertise": et_exp,
                                "Assigned Students": et_assign,
                                "Availability": et_sched_final
                            })
                            if success: 
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else: 
                                st.error(msg)

        # Row 4: Billing Manager (New)
        st.subheader("💳 Manage Student Billing")
        with st.expander("Update / Backfill Student Billing"):
            student_list = df_students["Student Name"].tolist()
            selected_student_bill = st.selectbox("Select Student", student_list, key="bill_student_select")
            
            # Form for update
            with st.form("billing_update_form"):
                c1, c2 = st.columns(2)
                with c1:
                    b_type = st.selectbox("Billing Type", ["Per Hour", "Per Class", "Monthly Fixed"], key="u_b_type")
                    b_rate = st.number_input("Rate / Amount", min_value=0.0, step=500.0, key="u_b_rate")
                with c2:
                    b_curr = st.radio("Currency", ["NGN", "USD"], horizontal=True, key="u_b_curr")
                    b_terms = st.selectbox("Payment Terms", ["Pre-paid", "Post-paid"], key="u_b_terms")
                
                recalc = st.checkbox("Recalculate Balance from History (Reviews)", help="Will count past classes from Reviews tab and update balance.")
                
                update_btn = st.form_submit_button("Update Profile")
                
                if update_btn:
                    success, msg = utils.update_billing_profile(client, selected_student_bill, {
                        "Billing Type": b_type,
                        "Rate": b_rate,
                        "Currency": b_curr,
                        "Payment Terms": b_terms
                    }, recalculate=recalc)
                    
                    if success:
                        st.success(f"✅ {msg}")
                    else:
                         st.error(f"❌ Failed: {msg}")

                    if success:
                        st.success(f"✅ {msg}")
                    else:
                         st.error(f"❌ Failed: {msg}")

        # Row 4: Teacher Payroll (New)
        st.subheader("👩‍🏫 Teacher Payroll")
        with st.expander("Calculate Teacher Payments"):
            df_teachers = utils.get_teacher_data(client)
            
            # Check if dataframe has data and the required 'Teacher Name' column
            # Based on user screenshot: 'Teacher Name', 'Phone Number', 'Subject Expertise', 'Class Schedule'
            if not df_teachers.empty and "Teacher Name" in df_teachers.columns:
                t_list = df_teachers["Teacher Name"].tolist()
                selected_t = st.selectbox("Select Teacher", t_list, key="pay_t_select")
                
                pay_share = st.number_input("Teacher Share (%)", min_value=0.0, max_value=100.0, value=70.0, step=5.0, key="pay_t_share")
                
                if st.button("Calculate Pay"):
                    # 1. Actual Pay (Retroactive from Reviews)
                    count, total_revenue, teacher_pay = utils.calculate_teacher_pay(client, selected_t, pay_share)
                    
                    # 2. Projected Pay (Forward-looking from Schedule)
                    # For projection, we need an estimated rate. Since rates vary per student, this is tricky.
                    # Simplified approach: Estimate Revenue using an Average Student Rate (e.g. 5000) for now, 
                    # or just show the class count projection.
                    
                    teacher_row = df_teachers[df_teachers["Teacher Name"] == selected_t].iloc[0]
                    schedule_str = str(teacher_row.get("Class Schedule", ""))
                    estimated_classes = utils.estimate_monthly_classes(schedule_str)
                    
                    # Rough projection: Assume average class value of 5000 NGN ?? 
                    # Better: Don't show money projection if we don't know who attends. 
                    # But user wants expectation. 
                    # Let's use a "Projected Base Revenue" if we had one. 
                    # For now, let's just show the Projected Classes count.
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.info(f"Classes Taught: {count}")
                        st.metric("Total Revenue Generated", f"NGN {total_revenue:,.2f}")
                        st.success(f"💰 Teacher Pay ({pay_share}%): NGN {teacher_pay:,.2f}")
                    
                    with c2:
                        st.info(f"Projected Monthly Classes: {estimated_classes}")
                        st.caption("Revenue projection requires knowing specific student attendance.")
            else:
                if df_teachers.empty:
                    st.warning("No teachers found. Please ensure the 'Teachers' tab exists and has data.")
                else:
                    st.error("The 'Teachers' tab is missing the 'Teacher Name' column. Please check your Google Sheet headers.")
                
                st.markdown("""
                **Detected Columns based on Screenshot:**
                - `Teacher Name` (Column A)
                - `Email` (Column B)
                - `Phone Number` (Column C)
                - `Subject Expertise` (Column D)
                - `Assigned Students` (Column E)
                - `Class Schedule` (Column F)
                """)

        # Row 5: Schedule Manager (New - Session System)
        st.subheader("📅 Schedule Manager")
        with st.expander("Schedule a New Class"):
            st.write("Create a session for the new Check-in System.")
            # Dropdowns
            teachers_list = df_teachers["Teacher Name"].tolist() if not df_teachers.empty and "Teacher Name" in df_teachers.columns else []
            students_list = df_students["Student Name"].tolist() if not df_students.empty else []
            
            with st.form("schedule_form"):
                sc_teacher = st.selectbox("Teacher", teachers_list)
                sc_student = st.selectbox("Student", students_list)
                
                # Subject Dropdown (Standard + Other)
                subject_opts = ["Maths", "English", "Physics", "Chemistry", "Biology", "Science", "History", "Geography", "Literacy", "Other"]
                sc_subject = st.selectbox("Subject", subject_opts)
                if sc_subject == "Other":
                    sc_subject = st.text_input("Enter Subject")
                
                sc_link = st.text_input("Meeting Link (Google Meet/Zoom)")
                
                c1, c2 = st.columns(2)
                sc_date = c1.date_input("Date")
                sc_time = c2.time_input("Time")
                
                if st.form_submit_button("Schedule & Send Invite"):
                    dt_str = f"{sc_date} {sc_time}"
                    
                    # Unpack 3 values now: Success, Msg, SessionID
                    success, msg, session_id_res = utils.schedule_class(client, sc_teacher, sc_student, sc_subject, dt_str, sc_link)
                    
                    if success:
                        if "Email Failed" in msg:
                            st.warning(f"⚠️ {msg}")
                            st.markdown("### 🔗 Manual Magic Links")
                            st.caption("Since email failed, please copy and send these links manually:")
                            
                            # Reconstruct Links using BASE_APP_URL from utils (hardcoded as localhost for now)
                            base = utils.BASE_APP_URL
                            link_t = f"{base}/?action=clock_in&session_id={session_id_res}&role=Teacher"
                            link_s = f"{base}/?action=clock_in&session_id={session_id_res}&role=Student"
                            
                            st.code(link_t, language="text")
                            st.caption("👆 Teacher Link")
                            st.code(link_s, language="text")
                            st.caption("👆 Student Link")
                        else:
                            st.success(f"✅ Class Scheduled! {msg}")
                    else:
                        st.error(f"❌ Failed: {msg}")

        # Row 6: Full Data View (Optional)
        with st.expander("View All Raw Data"):
            st.dataframe(df_students)
            
    else:
        st.info("No data to display.")

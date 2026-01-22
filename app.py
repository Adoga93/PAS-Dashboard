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

        # Display Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Students", len(df_students))
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

        # Apply style if column exists
        if "Payment Status" in df_students.columns:
            st.dataframe(df_students.style.applymap(highlight_status, subset=['Payment Status']), use_container_width=True)
        else:
            st.dataframe(df_students, use_container_width=True)
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
        with st.form("student_reg_form"):
            name = st.text_input("Full Name")
            email = st.text_input("Email")
            phone = st.text_input("Phone Number")
            class_times = st.text_input("Preferred Class Times")
            subjects = st.text_input("Subjects")
            
            submitted = st.form_submit_button("Register Student")
            
            if submitted:
                if name:
                    student_data = {
                        "Name": name,
                        "Email": email,
                        "Phone": phone,
                        "Class Times": class_times,
                        "Subjects": subjects
                    }
                    if utils.add_student(client, student_data):
                        st.success(f"✅ Student {name} registered successfully!")
                    else:
                        st.error("❌ Failed to register student.")
                else:
                    st.warning("Name is required.")

    elif reg_type == "Register Teacher":
        st.subheader("New Teacher Registration")
        with st.form("teacher_reg_form"):
            name = st.text_input("Full Name")
            email = st.text_input("Email")
            phone = st.text_input("Phone Number")
            expertise = st.text_input("Expertise (e.g. Math, Physics)")
            assigned_students = st.text_input("Assigned Students")
            
            submitted = st.form_submit_button("Register Teacher")
            
            if submitted:
                if name:
                    teacher_data = {
                        "Name": name,
                        "Email": email,
                        "Phone": phone,
                        "Expertise": expertise,
                        "Assigned Students": assigned_students
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

import streamlit as st
import pandas as pd
import plotly.express as px
import utils
import importlib
try:
    importlib.reload(utils)
except Exception:
    pass
import time
import datetime
import urllib.parse
import streamlit.components.v1 as components

PAS_BOARD_BASE_URL = "https://pas-recorder.duckdns.org/board"

def get_student_room_code(student_name):
    clean = "".join(ch for ch in str(student_name or "").upper() if ch.isalnum())
    return f"PAS{clean[:5]}" if clean else "PAS101"

def get_pas_board_link(room_code="PAS101", role="tutor", user_name="", title=""):
    clean_room = "".join(ch for ch in str(room_code).upper() if ch.isalnum())[:8] or "PAS101"
    params = {"room": clean_room, "role": role}
    if user_name:
        params["name"] = str(user_name).strip()
    if title:
        params["title"] = str(title).strip()
    return f"{PAS_BOARD_BASE_URL}/?{urllib.parse.urlencode(params)}"

def get_teacher_portal_link(teacher_name, base_url=None):
    if hasattr(utils, "generate_teacher_portal_link"):
        return utils.generate_teacher_portal_link(teacher_name, base_url)
    base = base_url or getattr(utils, "BASE_APP_URL", "https://pas-dashboard-gcvkbpip4geh7cchnpgqya.streamlit.app")
    base = base.rstrip('/')
    encoded = urllib.parse.quote_plus(str(teacher_name).strip())
    return f"{base}/?portal=teacher&t={encoded}"

st.set_page_config(page_title="PAS Tutors Dashboard", layout="wide")

# --- DATA LOADER ---
# Load client once (cache resource if needed, but simple for now)
client = utils.get_google_sheet_client()



if not client:
    st.warning("⚠️ Running in Mock Mode. `credentials.json` not found or invalid.")

# --- MAGIC LINK HANDLER (AUTO-CLOCK-IN & SURVEY) ---
# Check query params for action=clock_in or clock_out
query_params = st.query_params
action = query_params.get("action")

if action == "clock_in":
    session_id = query_params.get("session_id")
    role = query_params.get("role")
    student_name = query_params.get("student_name")
    
    st.title("🚀 Join Class")
    
    if session_id and role:
        success, msg, meeting_link = utils.clock_in_by_id(client, session_id, role, student_name)
        
        if success:
            st.balloons()
            st.success(f"✅ Welcome {role}! You are Clocked In.")
            st.markdown(f"### [👉 CLICK TO JOIN MEETING]({meeting_link})")
            st.caption("You may close this tab after joining.")
        else:
            st.error(f"❌ Error: {msg}")
    else:
        st.error("Invalid Link.")
    
    st.stop() # Stop rendering the rest of the app

elif action == "clock_out":
    session_id = query_params.get("session_id")
    role = query_params.get("role")
    
    if role != "Teacher":
        st.error("Only teachers can end the class and submit the survey.")
        st.stop()
        
    st.title("📝 End Class & Survey")
    
    # Check if already completed
    sessions_df = utils.get_sessions_data(client)
    if not sessions_df.empty:
        matches = sessions_df[sessions_df["Session ID"] == session_id]
        if not matches.empty:
            status = matches.iloc[0].get("Status")
            if status == "Completed":
                st.info("This class has already been ended and the survey submitted.")
                st.stop()
            
            subject = matches.iloc[0].get("Subject", "Unknown")
            
            with st.form("end_class_survey_form"):
                st.write(f"**Session ID:** {session_id}")
                st.write(f"**Subject:** {subject}")
                
                topic = st.text_input("Topic Taught")
                outcome = st.text_input("Learning Outcome")
                behaviour = st.selectbox("Learner's Behaviour", ["Excellent", "Good", "Fair", "Poor"])
                participation = st.selectbox("Learner's Participation", ["High", "Medium", "Low"])
                assignment_given = st.radio("Assignment Given?", ["Yes", "No"], horizontal=True)
                last_assignment = st.radio("Was last assignment done?", ["Yes", "No", "N/A"], horizontal=True)
                
                if st.form_submit_button("Submit Survey & End Class"):
                    survey_data = {
                        "Topic Taught": topic,
                        "Learning Outcome": outcome,
                        "Learner's Behaviour": behaviour,
                        "Learner's Participation": participation,
                        "Assignment Given": assignment_given,
                        "Last Assignment Done": last_assignment
                    }
                    
                    success, msg = utils.submit_survey(client, session_id, survey_data)
                    if success:
                        st.balloons()
                        st.success("✅ Survey submitted and class ended! You may close this tab.")
                    else:
                        st.error(f"❌ Error submitting survey: {msg}")
    else:
        st.error("Could not load sessions.")
    st.stop()

# --- DEDICATED TEACHER PORTAL (ISOLATED WORKSPACE) ---
# Check query params for teacher portal
portal_mode = query_params.get("portal")
teacher_param = query_params.get("t") or query_params.get("teacher") or query_params.get("teacher_id")

if portal_mode == "teacher" or teacher_param:
    # 1. Complete admin isolation - hide sidebar, header, navigation
    st.markdown("""
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stSidebarNav"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        header[data-testid="stHeader"] { visibility: hidden !important; }
        .block-container { padding-top: 1.5rem !important; max-width: 1100px !important; }
        
        /* Modern Teacher Dashboard Styling */
        .portal-header {
            background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
            padding: 24px 28px;
            border-radius: 16px;
            color: white;
            margin-bottom: 20px;
            box-shadow: 0 10px 25px -5px rgba(37, 99, 235, 0.25);
        }
        .profile-box {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .session-card {
            background: #ffffff;
            border-left: 5px solid #2563eb;
            border-radius: 10px;
            padding: 16px 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            margin-bottom: 14px;
            border-top: 1px solid #f1f5f9;
            border-right: 1px solid #f1f5f9;
            border-bottom: 1px solid #f1f5f9;
        }
        </style>
    """, unsafe_allow_html=True)
    
    df_teachers = utils.get_teacher_data(client)
    
    if not teacher_param:
        st.error("⚠️ Invalid Access: No teacher profile specified. Please use the personalized link provided by your administrator.")
        st.stop()
        
    # Match teacher
    # Match teacher with utils.normalize_name
    teacher_row = None
    if not df_teachers.empty and "Teacher Name" in df_teachers.columns:
        clean_param = utils.normalize_name(teacher_param)
        matches = df_teachers[df_teachers["Teacher Name"].apply(utils.normalize_name) == clean_param]
        if not matches.empty:
            teacher_row = matches.iloc[0]
            
    if teacher_row is None:
        st.error(f"❌ Teacher profile '{teacher_param}' not found. Please contact the administrator.")
        st.stop()
        
    teacher_name = str(teacher_row.get("Teacher Name", "")).strip()
    t_email = teacher_row.get("Email", "")
    t_expertise = teacher_row.get("Subject Expertise", "")
    
    # Week calculation & Weekend planning mode
    weeks_info = utils.get_available_planning_weeks()
    is_weekend = weeks_info["is_weekend"]
    
    if is_weekend:
        opt_upcoming = f"Upcoming Week: {weeks_info['upcoming_week']} (Default)"
        opt_current = f"Current Closing Week: {weeks_info['current_week']}"
        week_options = [opt_upcoming, opt_current]
        week_lookup = {
            opt_upcoming: weeks_info["upcoming_week"],
            opt_current: weeks_info["current_week"]
        }
    else:
        opt_current = f"Current Week: {weeks_info['current_week']} (Active)"
        opt_upcoming = f"Next Week: {weeks_info['upcoming_week']}"
        week_options = [opt_current, opt_upcoming]
        week_lookup = {
            opt_current: weeks_info["current_week"],
            opt_upcoming: weeks_info["upcoming_week"]
        }
        
    # Week selector controls
    c_hdr_left, c_hdr_right = st.columns([2, 1])
    with c_hdr_right:
        selected_week_label = st.selectbox("📅 Week to Confirm/View", week_options, index=0)
        selected_week = week_lookup[selected_week_label]
        
    # Fetch assigned students with their week plans for chosen week
    assigned_students = utils.get_teacher_assigned_students_details(client, teacher_name, week_range=selected_week)
    total_assigned = len(assigned_students)
    confirmed_count = sum(1 for s in assigned_students if (s.get("Current Week Plan") or {}).get("Status") == "Confirmed")
    
    # Fetch this teacher's scheduled/active classes (strictly isolated to current teacher)
    df_sessions = utils.get_sessions_data(client)
    my_sessions = pd.DataFrame()
    if not df_sessions.empty and "Teacher Name" in df_sessions.columns:
        clean_current_teacher = utils.normalize_name(teacher_name)
        my_sessions = df_sessions[
            (df_sessions["Teacher Name"].apply(utils.normalize_name) == clean_current_teacher) &
            (df_sessions["Status"].astype(str).str.strip().isin(["Scheduled", "In-Progress"]))
        ]
        
    active_class_count = len(my_sessions["Session ID"].unique()) if not my_sessions.empty and "Session ID" in my_sessions.columns else len(my_sessions)
    
    # Header Banner
    badge_title = "Upcoming Week" if (is_weekend and selected_week == weeks_info['upcoming_week']) else "Active Week"
    st.markdown(f"""
    <div class="portal-header">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <div>
                <h1 style="color: white; margin: 0; font-size: 26px; font-weight: 700;">Welcome, {teacher_name}! 👋</h1>
                <p style="margin: 6px 0 0 0; opacity: 0.95; font-size: 15px;">📚 Teacher Workspace • Weekly Lesson Planning & Confirmation</p>
            </div>
            <div style="text-align: right; background: rgba(255,255,255,0.18); padding: 8px 18px; border-radius: 10px; margin-top: 8px;">
                <span style="font-size: 12px; text-transform: uppercase; letter-spacing: 0.6px; opacity: 0.85;">{badge_title}</span><br>
                <strong style="font-size: 15px;">{selected_week}</strong>
            </div>
        </div>
        <div style="margin-top: 14px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.2); font-size: 13px; opacity: 0.9;">
            <span>📧 {t_email or 'No email recorded'}</span> &nbsp;•&nbsp; <span>🎯 Expertise: {t_expertise or 'General'}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if is_weekend and selected_week == weeks_info['upcoming_week']:
        st.info(f"🔔 **Weekend Planning Notice**: It is the weekend! You are confirming schedules and lesson plans for the upcoming week (**Monday to Sunday: {weeks_info['upcoming_week']}**).")
    
    # --- MASTER SCHEDULE LOGIC ---
    today_dt = datetime.date.today()
    today_day_name = today_dt.strftime("%A")
    today_display = today_dt.strftime("%A, %B %d, %Y")
    
    # Fetch all recurring classes for this teacher from the Master Schedule
    df_teacher_master = utils.get_teacher_master_schedule(client, teacher_name, selected_day=None)
    
    # Filter for today's classes
    df_teacher_today = pd.DataFrame()
    if not df_teacher_master.empty and "Day" in df_teacher_master.columns:
        df_teacher_today = df_teacher_master[df_teacher_master["Day"].str.lower() == today_day_name.lower()]
        
    today_count = len(df_teacher_today)
    total_weekly_count = len(df_teacher_master)

    # KPI Metrics Row
    m1, m2, m3, m4 = st.columns([1, 1, 1, 0.8])
    with m1:
        st.metric("👥 Assigned Students", f"{total_assigned}")
    with m2:
        st.metric(f"✅ Plans Confirmed ({selected_week})", f"{confirmed_count} / {total_assigned}")
    with m3:
        st.metric(f"📅 Today's Classes ({today_day_name})", f"{today_count}", help=f"{total_weekly_count} total recurring classes across the week")
    with m4:
        st.write("")
        if st.button("🔄 Refresh Data", key="t_portal_refresh_btn", use_container_width=True):
            for fn in [getattr(utils, 'get_teacher_data', None), 
                       getattr(utils, 'get_students_data', None), 
                       getattr(utils, 'get_weekly_plans_data', None), 
                       getattr(utils, 'get_sessions_data', None),
                       getattr(utils, 'get_teacher_master_schedule', None)]:
                if fn and hasattr(fn, 'clear'):
                    try:
                        fn.clear()
                    except Exception:
                        pass
            try:
                st.cache_data.clear()
            except Exception:
                pass
            st.rerun()

    st.markdown("---")

    # Primary Workspace Tabs
    portal_tab0, portal_tab1, portal_tab2, portal_tab3 = st.tabs([
        f"📅 Today's Schedule ({today_count})",
        "👥 My Students & Weekly Planning", 
        f"🚀 Weekly Master Schedule ({total_weekly_count})",
        "✏️ Interactive PAS Whiteboard"
    ])
    
    # TAB 0: TODAY'S CLASSES (DEFAULT VIEW)
    with portal_tab0:
        st.subheader(f"📅 Today's Class Schedule ({today_display})")
        
        if df_teacher_today.empty:
            st.info(f"🌴 **No classes scheduled for today ({today_display}).** Enjoy your day, or use the **Weekly Planning** tab to confirm upcoming sessions!")
        else:
            for _, c_row in df_teacher_today.iterrows():
                c_subj = c_row.get("Subject", "Class")
                c_st = c_row.get("Student", "Student")
                c_time = c_row.get("Time", "")
                c_end = c_row.get("EndTime", "")
                c_dur = c_row.get("Duration", "")
                c_link = str(c_row.get("MeetingLink", "")).strip()
                c_room = get_student_room_code(c_st)
                c_board_tutor = get_pas_board_link(c_room, "tutor", teacher_name, f"{c_subj} - {c_st}")
                c_board_student = get_pas_board_link(c_room, "student", c_st, f"{c_subj} - {c_st}")
                
                meet_btn_html = ""
                if c_link and (c_link.startswith("http://") or c_link.startswith("https://")):
                    meet_btn_html = f'<a href="{c_link}" target="_blank" style="display: inline-block; background: #2563eb; color: white; text-decoration: none; padding: 9px 16px; border-radius: 8px; font-weight: 600; font-size: 13px; margin-top: 6px; margin-right: 6px;">👉 Join Meeting Room</a>'
                else:
                    meet_btn_html = '<span style="color: #94a3b8; font-size: 13px; margin-right: 8px;">No meeting link attached</span>'
                
                board_btn_html = f'<a href="{c_board_tutor}" target="_blank" style="display: inline-block; background: #0f172a; color: #2dd4bf; border: 1px solid #14b8a6; text-decoration: none; padding: 8px 15px; border-radius: 8px; font-weight: 600; font-size: 13px; margin-top: 6px;">✏️ Open PAS Whiteboard ({c_room})</a>'
                    
                st.markdown(f"""
                <div style="background: white; border-left: 5px solid #2563eb; border-radius: 10px; padding: 18px 22px; margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); border-top: 1px solid #f1f5f9; border-right: 1px solid #f1f5f9; border-bottom: 1px solid #f1f5f9;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                        <div>
                            <span style="background: #2563eb; color: white; padding: 3px 12px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase;">⏳ Scheduled Today</span>
                            <h3 style="margin: 6px 0 6px 0; color: #0f172a; font-size: 19px; font-weight: 700;">{c_subj} with {c_st}</h3>
                            <p style="margin: 0; color: #475569; font-size: 14px;">⏰ Time: <strong>{c_time} - {c_end}</strong> ({c_dur}) &nbsp;•&nbsp; 🎨 Board Room: <code>{c_room}</code></p>
                        </div>
                        <div style="margin-top: 8px; text-align: right;">
                            {meet_btn_html}
                            {board_btn_html}
                            <div style="font-size: 11px; color: #64748b; margin-top: 5px;">Student Board Link: <a href="{c_board_student}" target="_blank" style="color: #0284c7;">{c_board_student}</a></div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    
    with portal_tab1:
        if not assigned_students:
            st.info("📋 You currently have no students assigned to you. When the administrator assigns students to you in the dashboard, they will appear here immediately.")
        else:
            student_names = [s["Student Name"] for s in assigned_students]
            
            # Manage active selected student in session_state
            if "selected_teacher_student" not in st.session_state or st.session_state["selected_teacher_student"] not in student_names:
                st.session_state["selected_teacher_student"] = student_names[0]
                
            st.subheader("📋 Select a Student to View Information & Plan")
            st.caption("Click on any student card below to open their full details and submit what you will teach this week:")
            
            # Student Cards Selector Grid
            num_cols = min(max(len(assigned_students), 1), 4)
            card_cols = st.columns(num_cols)
            
            for idx, s in enumerate(assigned_students):
                c_idx = idx % num_cols
                s_name = s["Student Name"]
                c_plan = s.get("Current Week Plan") or {}
                is_conf = (c_plan.get("Status") == "Confirmed")
                is_sel = (s_name == st.session_state["selected_teacher_student"])
                
                with card_cols[c_idx]:
                    status_text = "✅ Plan Confirmed" if is_conf else "⏳ Plan Needed"
                    status_color = "#16a34a" if is_conf else "#d97706"
                    card_border = "2px solid #2563eb" if is_sel else "1px solid #cbd5e1"
                    card_bg = "#eff6ff" if is_sel else "#ffffff"
                    
                    st.markdown(f"""
                    <div style="border: {card_border}; background: {card_bg}; padding: 14px 16px; border-radius: 12px; margin-bottom: 8px;">
                        <div style="font-size: 16px; font-weight: 700; color: #1e293b;">{s_name}</div>
                        <div style="font-size: 12px; font-weight: 600; color: {status_color}; margin-top: 2px;">{status_text}</div>
                        <div style="font-size: 12px; color: #64748b; margin-top: 4px;">Times: {s.get('Class Times') or 'Not set'}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    button_label = f"⭐ Viewing {s_name}" if is_sel else f"Select {s_name}"
                    if st.button(button_label, key=f"sel_student_btn_{idx}", use_container_width=True, type="primary" if is_sel else "secondary"):
                        st.session_state["selected_teacher_student"] = s_name
                        st.rerun()

            st.markdown("---")
            
            # DETAILED WORKSPACE FOR THE SELECTED STUDENT
            selected_student_name = st.session_state["selected_teacher_student"]
            student_data = next((s for s in assigned_students if s["Student Name"] == selected_student_name), assigned_students[0])
            curr_plan = student_data.get("Current Week Plan") or {}
            is_confirmed = (curr_plan.get("Status") == "Confirmed")
            
            default_time = curr_plan.get("Confirmed Class Time") or student_data.get("Class Times") or ""
            default_subject = curr_plan.get("Subject") or student_data.get("Subjects") or ""
            default_topic = curr_plan.get("Topic / Curriculum") or ""
            default_link = curr_plan.get("Meeting Link") or ""
            
            st.markdown(f"### 👤 {selected_student_name} — Details & Lesson Confirmation")
            
            # Master-Detail Layout: Profile on Left, Confirmation Form on Right
            c_left, c_right = st.columns([1, 1.4])
            
            with c_left:
                st.markdown("##### 📌 Student Information")
                st.markdown(f"""
                <div class="profile-box">
                    <p style="margin: 0 0 8px 0; font-size: 16px;"><strong>👤 Name:</strong> {selected_student_name}</p>
                    <p style="margin: 0 0 8px 0;"><strong>📧 Email:</strong> {student_data.get('Email') or 'Not recorded'}</p>
                    <p style="margin: 0 0 8px 0;"><strong>📞 Phone:</strong> {student_data.get('Phone') or 'Not recorded'}</p>
                    <p style="margin: 0 0 8px 0;"><strong>⏰ Preferred Class Times:</strong><br><code>{student_data.get('Class Times') or 'Not set'}</code></p>
                    <p style="margin: 0 0 8px 0;"><strong>📚 Subjects:</strong> {student_data.get('Subjects') or 'General'}</p>
                    <p style="margin: 0 0 8px 0;"><strong>📈 Academic Progress:</strong> {student_data.get('Academic Progress', 'N/A')}%</p>
                    <p style="margin: 0 0 0 0;"><strong>🗓️ Attendance:</strong> {student_data.get('Attendance', 'N/A')}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if is_confirmed:
                    st.success("##### ✅ Weekly Plan Confirmed")
                    st.markdown(f"""
                    - **Confirmed Time:** `{default_time}`
                    - **Topic:** {default_topic or 'None entered'}
                    """)
                    if default_link:
                        st.markdown(f"[👉 **Click to Launch Class Meeting**]({default_link})")
                else:
                    st.warning("⚠️ **Plan Needed**: Please confirm the class day/time and curriculum for this week in the form.")
                    
            with c_right:
                st.markdown("##### ✏️ Weekly Plan Confirmation Form")
                with st.form(key=f"form_plan_{selected_student_name}"):
                    c_f1, c_f2 = st.columns([2, 1])
                    new_time = c_f1.text_input(
                        "Confirmed Class Day & Time for this Week", 
                        value=default_time, 
                        help="e.g. 'Monday 4:00 PM, Thursday 4:00 PM'"
                    )
                    new_sub = c_f2.text_input("Subject", value=default_subject)
                    
                    new_topic = st.text_area(
                        "What will you be teaching this week? (Topic & Curriculum)",
                        value=default_topic,
                        placeholder="e.g. Algebra: Solving Linear & Quadratic Equations; Review of past exercises.",
                        help="Outline the topics, curriculum, and goals you will cover with this student this week."
                    )
                    
                    st.markdown("**Meeting Link (Zoom, Google Meet, Teams, etc.)**")
                    c_link, c_auto = st.columns([3, 2])
                    new_link = c_link.text_input(
                        "Paste / Upload Meeting Link",
                        value=default_link,
                        placeholder="https://meet.google.com/... or https://zoom.us/j/...",
                        help="Paste your own meeting link here."
                    )
                    auto_gen = c_auto.checkbox("Auto-generate Google Meet if empty", value=False, key=f"auto_meet_sel_{selected_student_name}")
                    
                    submitted = st.form_submit_button(f"✅ Save & Confirm Plan for {selected_student_name}", use_container_width=True, type="primary")
                    
                    if submitted:
                        final_link = new_link.strip()
                        if not final_link and auto_gen:
                            start_dt = datetime.datetime.now() + datetime.timedelta(hours=2)
                            end_dt = start_dt + datetime.timedelta(hours=1)
                            attendees = [t_email]
                            if student_data.get("Email"):
                                attendees.append(student_data["Email"])
                            gen_link = utils.generate_meet_link(f"PAS Tutoring - {selected_student_name} ({new_sub})", start_dt, end_dt, attendees)
                            if gen_link:
                                final_link = gen_link
                                st.info(f"Generated Google Meet link: {final_link}")
                            else:
                                st.warning("Could not auto-generate Google Meet link. Please paste a meeting link manually.")
                                
                        success, msg = utils.save_weekly_plan(
                            client, selected_week, teacher_name, selected_student_name,
                            new_sub, new_time, new_topic, final_link, status="Confirmed"
                        )
                        if success:
                            st.success(f"✅ Schedule and lesson plan confirmed for {selected_student_name}!")
                            time.sleep(0.6)
                            st.rerun()
                        else:
                            st.error(f"❌ Error saving plan: {msg}")

    # TAB 2: ACTIVE & SCHEDULED CLASSES FOR THIS TEACHER ONLY
    with portal_tab2:
        st.subheader(f"🚀 Weekly Master Schedule ({total_weekly_count} Total Classes)")
        st.caption("All recurring weekly classes for your assigned students according to the Master Schedule.")
        
        day_filter = st.radio(
            "Filter Schedule by Day:", 
            ["All Days", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], 
            horizontal=True,
            index=0
        )
        
        filtered_sched = df_teacher_master
        if day_filter != "All Days" and not df_teacher_master.empty:
            filtered_sched = df_teacher_master[df_teacher_master["Day"].str.lower() == day_filter.lower()]
            
        if filtered_sched.empty:
            st.info(f"No classes scheduled for {day_filter}.")
        else:
            for _, c_row in filtered_sched.iterrows():
                c_day = c_row.get("Day", "")
                c_subj = c_row.get("Subject", "Class")
                c_st = c_row.get("Student", "Student")
                c_time = c_row.get("Time", "")
                c_end = c_row.get("EndTime", "")
                c_dur = c_row.get("Duration", "")
                c_link = str(c_row.get("MeetingLink", "")).strip()
                
                meet_btn_html = ""
                if c_link and (c_link.startswith("http://") or c_link.startswith("https://")):
                    meet_btn_html = f'<a href="{c_link}" target="_blank" style="display: inline-block; background: #2563eb; color: white; text-decoration: none; padding: 7px 14px; border-radius: 6px; font-weight: 600; font-size: 12px;">👉 Join Meeting Room</a>'
                else:
                    meet_btn_html = '<span style="color: #94a3b8; font-size: 12px;">No link attached</span>'
                    
                st.markdown(f"""
                <div style="background: white; border-left: 4px solid #3b82f6; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px; box-shadow: 0 1px 6px rgba(0,0,0,0.04); border-top: 1px solid #f1f5f9; border-right: 1px solid #f1f5f9; border-bottom: 1px solid #f1f5f9;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                        <div>
                            <span style="background: #f1f5f9; color: #334155; padding: 2px 10px; border-radius: 8px; font-size: 11px; font-weight: 700;">{c_day}</span>
                            <h4 style="margin: 6px 0 4px 0; color: #0f172a; font-size: 16px; font-weight: 600;">{c_subj} with {c_st}</h4>
                            <p style="margin: 0; color: #64748b; font-size: 13px;">⏰ {c_time} - {c_end} ({c_dur})</p>
                        </div>
                        <div style="margin-top: 6px; text-align: right;">
                            {meet_btn_html}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        # --- SECTION: STUDENT MONTHLY EVALUATIONS & CONFIRMATION ---
        st.markdown("---")
        st.subheader("📋 Student Monthly Evaluations & Confirmation")
        st.caption("Review your assigned students' recorded class reports, edit remarks, and confirm monthly reports for Head Teacher approval.")

        if assigned_students:
            t_student_names = [s.get("Student Name") for s in assigned_students if s.get("Student Name")]
            sel_tp_student = st.selectbox("Select Student for Monthly Review", t_student_names, key="tp_sel_student")
            
            # Month selection
            curr_month_str = datetime.date.today().strftime("%B %Y")
            tp_month = st.selectbox("Evaluation Month", [curr_month_str, "September 2026", "November 2026"], index=0, key="tp_sel_month")
            
            # Fetch existing monthly report
            df_m_all = utils.get_monthly_reports_data(client)
            s_norm = utils.normalize_name(sel_tp_student)
            
            existing_m = pd.DataFrame()
            if not df_m_all.empty and "Student Name" in df_m_all.columns:
                existing_m = df_m_all[
                    (df_m_all["Student Name"].apply(utils.normalize_name) == s_norm) &
                    (df_m_all["Month"].str.strip().str.lower() == tp_month.strip().lower())
                ]
                
            c_tp_gen, c_tp_info = st.columns([1, 2])
            with c_tp_gen:
                if st.button("⚡ Generate / Refresh Monthly Draft", key="tp_btn_draft"):
                    draft = utils.generate_monthly_report_draft(client, sel_tp_student, tp_month)
                    draft["Teacher Name"] = teacher_name
                    succ, msg = utils.save_monthly_report(client, draft)
                    if succ:
                        st.success("Draft generated from class recordings!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"Error: {msg}")
                        
            if not existing_m.empty:
                m_row = existing_m.iloc[0].to_dict()
                m_status = m_row.get("Status", "Draft")
                m_id = m_row.get("Monthly Report ID")
                
                status_color = "🟢" if m_status == "Approved by Head Teacher" else "🔵" if m_status == "Confirmed by Teacher" else "🟡"
                st.info(f"**Status:** {status_color} **{m_status}** • **Classes:** {m_row.get('Total Classes')} ({m_row.get('Total Hours')} hrs)")
                
                with st.form(f"tp_edit_m_form_{m_id}"):
                    st.markdown("#### ✏️ Review & Edit Monthly Report Content")
                    tp_curriculum = st.text_area("Curriculum & Topics Covered", value=m_row.get("Curriculum Covered", ""), height=100)
                    tp_hw = st.text_area("Homework & Independent Practice", value=m_row.get("Homework Rating", ""), height=80)
                    tp_comp = st.text_area("Concept Comprehension & Attitude", value=m_row.get("Comprehension & Progress", ""), height=80)
                    tp_t_remarks = st.text_area("Teacher Remarks & Observations", value=m_row.get("Teacher Remarks", ""), height=100)
                    
                    c_save, c_confirm = st.columns(2)
                    with c_save:
                        submit_save = st.form_submit_button("💾 Save My Edits")
                    with c_confirm:
                        submit_confirm = st.form_submit_button("✍️ Confirm & Submit to Head Teacher")
                        
                    if submit_save:
                        m_row["Curriculum Covered"] = tp_curriculum
                        m_row["Homework Rating"] = tp_hw
                        m_row["Comprehension & Progress"] = tp_comp
                        m_row["Teacher Remarks"] = tp_t_remarks
                        m_row["Teacher Name"] = teacher_name
                        succ, msg = utils.save_monthly_report(client, m_row)
                        if succ:
                            st.success("Changes saved successfully!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"Save failed: {msg}")
                            
                    if submit_confirm:
                        succ, msg = utils.confirm_monthly_report_teacher(client, m_id, teacher_name, tp_t_remarks)
                        if succ:
                            st.balloons()
                            st.success("✅ Monthly report confirmed! Submitted to Head Teacher for final approval.")
                            time.sleep(0.7)
                            st.rerun()
                        else:
                            st.error(f"Confirmation failed: {msg}")
                            
                # Downloadable preview
                html_preview = utils.generate_monthly_report_html(m_row)
                st.download_button(
                    label="📥 Download Printable Report (HTML / PDF)",
                    data=html_preview,
                    file_name=f"PAS_Report_{sel_tp_student}_{tp_month}.html",
                    mime="text/html",
                    key=f"tp_dl_{m_id}"
                )
            else:
                st.info("No monthly report generated yet for this student. Click 'Generate / Refresh Monthly Draft' above to aggregate their class reports.")

    # TAB 3: INTERACTIVE PAS WHITEBOARD FOR THIS TEACHER
    with portal_tab3:
        st.subheader("✏️ PAS Interactive Classroom Whiteboard")
        st.caption("Write, draw on 4-line handwriting or math grids, import PDF worksheets, and collaborate live in real time with your students.")
        
        wb_col1, wb_col2, wb_col3 = st.columns([1.5, 1, 1.5])
        with wb_col1:
            wb_student_opts = [s.get("Student Name") for s in assigned_students if s.get("Student Name")] if assigned_students else ["General Classroom"]
            sel_wb_student = st.selectbox("Select Student Classroom", wb_student_opts, key="tp_wb_student")
        with wb_col2:
            default_wb_room = get_student_room_code(sel_wb_student) if sel_wb_student != "General Classroom" else "PAS101"
            wb_room_code = st.text_input("Classroom Code", value=default_wb_room, key=f"tp_wb_room_{sel_wb_student}").strip().upper()
        with wb_col3:
            tutor_wb_url = get_pas_board_link(wb_room_code, "tutor", teacher_name, f"PAS Session - {sel_wb_student}")
            student_wb_url = get_pas_board_link(wb_room_code, "student", sel_wb_student, f"PAS Session - {sel_wb_student}")
            st.markdown(f"""
            <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px 14px; font-size: 12px;">
                <div><strong>🎨 Fullscreen Tutor Board:</strong> <a href="{tutor_wb_url}" target="_blank" style="color: #2563eb; font-weight: 700;">Open in New Tab ↗</a></div>
                <div style="margin-top: 4px;"><strong>🎓 Student Invite Link:</strong> <a href="{student_wb_url}" target="_blank" style="color: #0d9488; font-weight: 600;">{student_wb_url}</a></div>
            </div>
            """, unsafe_allow_html=True)
            
        components.iframe(src=tutor_wb_url, height=820, scrolling=True)
                
    st.stop() # CRITICAL: Teacher cannot view or execute admin dashboard


# --- SIDEBAR ---
st.sidebar.title("PAS Tutors")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Sync with Database (Refresh)"):
    utils.get_students_data.clear()
    utils.get_teacher_data.clear()
    utils.get_billing_data.clear()
    utils.get_sessions_data.clear()
    st.sidebar.success("Cache cleared! Reloading fresh data...")
    time.sleep(0.5)
    st.rerun()

st.sidebar.markdown("---")
tab = st.sidebar.radio("Navigate to", ["Student Tab", "Teacher Tab", "✏️ PAS Whiteboard", "Registration", "Class & Monthly Reports", "Admin Dashboard"])

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
        
        # Calculate Total Outstanding Balance from Dynamic Calculation
        df_balances = utils.get_all_student_balances(client)
        total_outstanding = 0.0
        if not df_balances.empty:
            # ensure 'Total Owed' is numeric
            total_outstanding = df_balances["Total Owed"].sum()
        
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
                df_display.style.map(highlight_status, subset=['Payment Status']),
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



    # --- STUDENT CLASS REPORTS & MONTHLY EVALUATION DRILL-DOWN ---
    st.markdown("---")
    st.subheader("📚 Student Recorded Class Reports & Monthly Evaluations")
    with st.expander("🔍 View & Manage Individual Student Reports", expanded=False):
        if not df_students.empty and "Student Name" in df_students.columns:
            st_names_list = sorted([s for s in df_students["Student Name"].dropna().unique() if str(s).strip()])
            selected_student_report = st.selectbox("Choose Student to View Reports", st_names_list, key="st_tab_sel_student")
            
            if selected_student_report:
                s_norm = utils.normalize_name(selected_student_report)
                df_c_all = utils.get_class_reports_data(client)
                df_m_all = utils.get_monthly_reports_data(client)
                
                # Match class reports
                s_class_reports = pd.DataFrame()
                if not df_c_all.empty and "Student Name" in df_c_all.columns:
                    s_class_reports = df_c_all[df_c_all["Student Name"].apply(utils.normalize_name) == s_norm]
                    
                # Match monthly reports
                s_monthly_reports = pd.DataFrame()
                if not df_m_all.empty and "Student Name" in df_m_all.columns:
                    s_monthly_reports = df_m_all[df_m_all["Student Name"].apply(utils.normalize_name) == s_norm]
                    
                col_c1, col_c2 = st.columns(2)
                col_c1.metric("Recorded Class Sessions", len(s_class_reports))
                col_c2.metric("Monthly Evaluations", len(s_monthly_reports))
                
                tab_rep1, tab_rep2 = st.tabs(["📝 Recorded Class Sessions", "📊 Monthly Reports"])
                
                with tab_rep1:
                    if s_class_reports.empty:
                        st.info(f"No recorded class session reports found for {selected_student_report} yet.")
                    else:
                        for _, c_rep in s_class_reports.iterrows():
                            r_date = c_rep.get("Date", "N/A")
                            r_subj = c_rep.get("Subject", "General")
                            r_topic = c_rep.get("Topic", "Lesson")
                            r_teacher = c_rep.get("Teacher Name", "Tutor")
                            r_id = c_rep.get("Report ID")
                            
                            with st.expander(f"📅 {r_date} • {r_subj}: {r_topic} (Teacher: {r_teacher})"):
                                st.markdown(f"**Executive Summary:** {c_rep.get('Executive Summary', 'N/A')}")
                                
                                c_l, c_r = st.columns(2)
                                with c_l:
                                    st.markdown("**Curriculum Covered:**")
                                    st.write(utils._safe_json_loads(c_rep.get("Curriculum Breakdown")))
                                with c_r:
                                    st.markdown("**Homework & Tasks:**")
                                    st.write(utils._safe_json_loads(c_rep.get("Homework Tracking")))
                                    
                with tab_rep2:
                    if s_monthly_reports.empty:
                        st.info(f"No monthly reports compiled for {selected_student_report} yet. You can generate one in the 'Class & Monthly Reports' tab.")
                    else:
                        for _, m_rep in s_monthly_reports.iterrows():
                            m_month = m_rep.get("Month", "")
                            m_status = m_rep.get("Status", "Draft")
                            m_id = m_rep.get("Monthly Report ID")
                            status_badge = "🟢" if m_status == "Approved by Head Teacher" else "🔵" if m_status == "Confirmed by Teacher" else "🟡"
                            
                            with st.expander(f"{status_badge} {m_month} Report • Status: {m_status}"):
                                st.write(f"**Teacher Remarks:** {m_rep.get('Teacher Remarks')}")
                                st.write(f"**Head Teacher Comments:** {m_rep.get('Head Teacher Recommendations')}")
                                
                                html_dl = utils.generate_monthly_report_html(m_rep.to_dict())
                                st.download_button(
                                    "📥 Download Printable Evaluation (HTML / PDF)",
                                    data=html_dl,
                                    file_name=f"PAS_Report_{selected_student_report}_{m_month}.html",
                                    mime="text/html",
                                    key=f"st_dl_m_{m_id}"
                                )

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

    st.markdown("---")
    st.subheader("✏️ Interactive PAS Classroom Whiteboard")
    with st.expander("🎨 Join Live PAS Whiteboard Session (Students & Tutors)", expanded=True):
        df_st_wb = utils.get_students_data(client)
        st_wb_names = sorted([s for s in df_st_wb["Student Name"].dropna().unique() if str(s).strip()]) if not df_st_wb.empty and "Student Name" in df_st_wb.columns else []
        c_swb1, c_swb2, c_swb3 = st.columns([1.5, 1, 1])
        with c_swb1:
            sel_st_wb = st.selectbox("Select Your Name (or Custom Room)", ["Custom Room Code"] + st_wb_names, key="st_portal_wb_sel")
        with c_swb2:
            def_st_room = get_student_room_code(sel_st_wb) if sel_st_wb != "Custom Room Code" else "PAS101"
            st_room_input = st.text_input("Classroom Room Code", value=def_st_room, key=f"st_wb_code_{sel_st_wb}").strip().upper()
        with c_swb3:
            st_role_choice = st.radio("Join As", ["student", "tutor"], format_func=lambda r: "🎓 Student" if r == "student" else "👨‍🏫 PAS Tutor", horizontal=True, key="st_wb_role")
        
        st_display_name = sel_st_wb if sel_st_wb != "Custom Room Code" else ("Student" if st_role_choice == "student" else "PAS Tutor")
        live_wb_url = get_pas_board_link(st_room_input, st_role_choice, st_display_name)
        st.markdown(f"👉 **[Open Fullscreen PAS Whiteboard in New Tab ({st_room_input})]({live_wb_url})** &nbsp;•&nbsp; Shareable Student Link: `{get_pas_board_link(st_room_input, 'student')}`")
        if st.checkbox("Embed Interactive Whiteboard directly on this page", value=False, key="st_tab_embed_wb"):
            components.iframe(src=live_wb_url, height=820, scrolling=True)

# --- PAS WHITEBOARD TAB ---
elif tab == "✏️ PAS Whiteboard":
    st.header("✏️ PAS Board — Live Interactive Classroom Whiteboard")
    st.caption("Real-time multiplayer Jamboard with 4-line primary handwriting guides, early learner boxed sheets, math grids, PDF worksheet import, and 150% comfort zoom.")
    
    df_st_board = utils.get_students_data(client)
    st_board_names = sorted([s for s in df_st_board["Student Name"].dropna().unique() if str(s).strip()]) if not df_st_board.empty and "Student Name" in df_st_board.columns else []
    
    b_col1, b_col2, b_col3, b_col4 = st.columns([1.4, 1, 1, 1.6])
    with b_col1:
        sel_board_student = st.selectbox("Select Student Classroom", ["General Room (PAS101)"] + st_board_names, key="main_wb_student")
    with b_col2:
        default_main_room = get_student_room_code(sel_board_student) if sel_board_student != "General Room (PAS101)" else "PAS101"
        main_room_code = st.text_input("Room Code", value=default_main_room, key=f"main_wb_room_{sel_board_student}").strip().upper()
    with b_col3:
        main_role = st.radio("Role", ["tutor", "student"], format_func=lambda r: "👨‍🏫 Tutor" if r == "tutor" else "🎓 Student", horizontal=True, key="main_wb_role")
    with b_col4:
        main_board_url = get_pas_board_link(main_room_code, main_role, sel_board_student if main_role == "student" and sel_board_student != "General Room (PAS101)" else "")
        student_share_url = get_pas_board_link(main_room_code, "student", sel_board_student if sel_board_student != "General Room (PAS101)" else "")
        st.markdown(f"""
        <div style="background: #0f172a; color: white; border-radius: 10px; padding: 10px 14px; font-size: 12px;">
            <div>🚀 <a href="{main_board_url}" target="_blank" style="color: #2dd4bf; font-weight: 700; text-decoration: none;">Open Fullscreen Board in New Tab ↗</a></div>
            <div style="margin-top: 4px; color: #cbd5e1;">🔗 Student Link: <a href="{student_share_url}" target="_blank" style="color: #38bdf8;">{student_share_url}</a></div>
        </div>
        """, unsafe_allow_html=True)
        
    components.iframe(src=main_board_url, height=840, scrolling=True)

# --- TEACHER TAB ---
elif tab == "Teacher Tab":
    st.header("🍎 Teacher Check-in")
    st.markdown("Please submit your class review below.")
    
    with st.form("checkin_form"):
        # Fetch teacher list
        df_teachers_list = utils.get_teacher_data(client)
        teacher_options = df_teachers_list["Teacher Name"].tolist() if not df_teachers_list.empty and "Teacher Name" in df_teachers_list.columns else []
        
        if teacher_options:
            teacher_name = st.selectbox("Your Name", teacher_options)
        else:
            teacher_name = st.text_input("Your Name", help="Selectbox disabled: No teachers found.")
        
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
                # Group by Session ID to handle multi-student classes
                grouped_classes = my_classes.groupby("Session ID", as_index=False).agg({
                    "Subject": "first",
                    "Student Name": lambda x: ", ".join(x.astype(str)),
                    "Scheduled Time": "first",
                    "Status": "first",
                    "Attendance Code": "first",
                    "Meeting Link": "first"
                })
                
                st.write(f"You have {len(grouped_classes)} upcoming/active classes.")
                
                for index, row in grouped_classes.iterrows():
                    with st.container():
                        st.info(f"**{row['Subject']}** with {row['Student Name']} @ {row['Scheduled Time']}")
                        status = row['Status']
                        s_id = row['Session ID']
                        
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.write(f"Status: **{status}**")
                        
                        with c2:
                            if status in ["Scheduled", "In-Progress"]:
                                st.markdown(f"### 🔑 CODE: `{row.get('Attendance Code', 'N/A')}`")
                                meet_link = row.get("Meeting Link", "")
                                if meet_link and str(meet_link).strip():
                                     st.markdown(f"[Join Meeting]({meet_link})")
                        
                        with c3:
                            if status in ["Scheduled", "In-Progress"]:
                                # Since teachers now use the Magic Link survey, we provide the link here too
                                # just in case they don't have their email handy.
                                magic_link_end = f"{utils.BASE_APP_URL}/?action=clock_out&session_id={s_id}&role=Teacher"
                                st.markdown(f"**[📝 END CLASS & SURVEY]({magic_link_end})**")
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
        
        subject_options = utils.STANDARD_SUBJECTS
        day_options = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        df_teachers_list = utils.get_teacher_data(client)
        teacher_options = ["Unassigned"]
        if not df_teachers_list.empty and "Teacher Name" in df_teachers_list.columns:
            teacher_options.extend(df_teachers_list["Teacher Name"].tolist())
            
        all_subjects_data = []
        
        for i in range(st.session_state.reg_subject_rows):
            c1, c2, c3, c4, c5, c6 = st.columns([3, 3, 2, 2, 2, 1])
            with c1:
                sub = st.selectbox(f"Subject {i+1}", subject_options, key=f"sub_{i}")
            with c2:
                tcher = st.selectbox(f"Teacher {i+1}", teacher_options, key=f"eteach_{i}")
            with c3:
                day = st.selectbox(f"Day {i+1}", day_options, key=f"day_{i}")
            with c4:
                start_t = st.time_input(f"Start {i+1}", value=datetime.time(9, 0), key=f"start_{i}")
            with c5:
                end_t = st.time_input(f"End {i+1}", value=datetime.time(10, 0), key=f"end_{i}")
            with c6:
                st.markdown("<br>", unsafe_allow_html=True) # Align with input boxes
                is_deleted = st.checkbox("🗑️", key=f"del_{i}")
            
            if not is_deleted:
                all_subjects_data.append({
                    "Subject": sub,
                    "Teacher": tcher,
                    "Day": day,
                    "StartTime": start_t,
                    "EndTime": end_t
                })

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
                subject_list = list(set([entry['Subject'] for entry in all_subjects_data]))
                subjects_str = ", ".join(subject_list)
                
                selected_teachers = list(set([entry["Teacher"] for entry in all_subjects_data if entry["Teacher"] != "Unassigned"]))
                
                class_times_parts = []
                for entry in all_subjects_data:
                    s_str = entry['StartTime'].strftime("%I:%M %p")
                    e_str = entry['EndTime'].strftime("%I:%M %p")
                    teacher_str = f" [{entry['Teacher']}]" if entry.get('Teacher') and entry['Teacher'] != "Unassigned" else ""
                    class_times_parts.append(f"{entry['Subject']} ({entry['Day'][:3]} {s_str} - {e_str}){teacher_str}")
                
                class_times_str = ", ".join(class_times_parts)
                
                student_data = {
                    "Name": name,
                    "Email": email,
                    "Phone": phone,
                    "Class Times": class_times_str,
                    "Subjects": subjects_str,
                    "Selected Teachers": selected_teachers
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
        subject_options = utils.STANDARD_SUBJECTS
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

# --- CLASS & MONTHLY REPORTS TAB ---
elif tab == "Class & Monthly Reports":
    st.header("📑 Student Class & Monthly Progress Reports")
    st.caption("Review recording bot class session analyses, edit pedagogical remarks, confirm monthly evaluations (Teacher ➔ Head Teacher), and export parent-ready reports.")

    df_students_all = utils.get_students_data(client)
    df_teachers_all = utils.get_teacher_data(client)
    df_class_reps = utils.get_class_reports_data(client)
    df_monthly_reps = utils.get_monthly_reports_data(client)

    # Top KPI Metrics
    total_class_reps = len(df_class_reps)
    students_with_reps = df_class_reps["Student Name"].nunique() if not df_class_reps.empty and "Student Name" in df_class_reps.columns else 0
    pending_teacher = len(df_monthly_reps[df_monthly_reps["Status"] == "Draft"]) if not df_monthly_reps.empty and "Status" in df_monthly_reps.columns else 0
    pending_head = len(df_monthly_reps[df_monthly_reps["Status"] == "Confirmed by Teacher"]) if not df_monthly_reps.empty and "Status" in df_monthly_reps.columns else 0
    ready_parents = len(df_monthly_reps[df_monthly_reps["Status"] == "Approved by Head Teacher"]) if not df_monthly_reps.empty and "Status" in df_monthly_reps.columns else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📹 Recorded Class Sessions", total_class_reps)
    m2.metric("⏳ Awaiting Teacher Sign-off", pending_teacher)
    m3.metric("👑 Awaiting Head Teacher", pending_head)
    m4.metric("✅ Ready for Parents", ready_parents)

    st.markdown("---")
    subtab_sessions, subtab_monthly = st.tabs([
        "📝 Individual Recorded Class Reports", 
        "📊 Consolidated Monthly Reports & Sign-off"
    ])

    # ========================================================
    # SUBTAB 1: INDIVIDUAL CLASS SESSION REPORTS
    # ========================================================
    with subtab_sessions:
        c_sync1, c_sync2 = st.columns([3, 1])
        with c_sync1:
            st.subheader("Class Session Pedagogical Reports")
            st.caption("Detailed AI analyses generated by the meeting recording bot for each class session.")
        with c_sync2:
            if st.button("🔄 Sync with Recording Bot", help="Checks local recordings/reports folder and updates Google Sheet"):
                utils.get_class_reports_data.clear()
                st.success("Synced! Refreshing reports...")
                time.sleep(0.5)
                st.rerun()

        # Filters
        st_filter_options = ["All Students"]
        if not df_students_all.empty and "Student Name" in df_students_all.columns:
            st_filter_options.extend(sorted([s for s in df_students_all["Student Name"].dropna().unique() if str(s).strip()]))

        col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
        with col_f1:
            sel_filter_st = st.selectbox("Filter by Student", st_filter_options, key="cr_filter_student")
        with col_f2:
            subj_filter_options = ["All Subjects"] + utils.STANDARD_SUBJECTS
            sel_filter_subj = st.selectbox("Filter by Subject", subj_filter_options, key="cr_filter_subj")
        with col_f3:
            search_rep_kw = st.text_input("🔍 Search Keyword (Topic, notes)", "", key="cr_search_kw")

        # Filter data
        filtered_reps = df_class_reps.copy() if not df_class_reps.empty else pd.DataFrame()
        if not filtered_reps.empty:
            if sel_filter_st != "All Students":
                filtered_reps = filtered_reps[filtered_reps["Student Name"].apply(utils.normalize_name) == utils.normalize_name(sel_filter_st)]
            if sel_filter_subj != "All Subjects" and "Subject" in filtered_reps.columns:
                filtered_reps = filtered_reps[filtered_reps["Subject"].str.lower() == sel_filter_subj.lower()]
            if search_rep_kw and "Topic" in filtered_reps.columns:
                kw = search_rep_kw.lower()
                filtered_reps = filtered_reps[
                    filtered_reps["Topic"].str.lower().str.contains(kw, na=False) |
                    filtered_reps["Executive Summary"].str.lower().str.contains(kw, na=False) |
                    filtered_reps["Student Name"].str.lower().str.contains(kw, na=False)
                ]

        # Add manual report expander
        with st.expander("➕ Add Manual Class Report (For unrecorded or external classes)", expanded=False):
            with st.form("manual_class_report_form"):
                st.markdown("##### New Class Report Details")
                st_list_man = [s for s in df_students_all["Student Name"].dropna().unique() if str(s).strip()] if not df_students_all.empty else ["Student"]
                t_list_man = [t for t in df_teachers_all["Teacher Name"].dropna().unique() if str(t).strip()] if not df_teachers_all.empty else ["Teacher"]
                
                c_m1, c_m2, c_m3 = st.columns(3)
                with c_m1:
                    man_st = st.selectbox("Student Name", st_list_man, key="man_st")
                with c_m2:
                    man_t = st.selectbox("Teacher Name", t_list_man, key="man_t")
                with c_m3:
                    man_subj = st.selectbox("Subject", utils.STANDARD_SUBJECTS, key="man_subj")
                    
                c_m4, c_m5, c_m6 = st.columns(3)
                with c_m4:
                    man_date = st.date_input("Class Date", value=datetime.date.today(), key="man_date")
                with c_m5:
                    man_dur = st.selectbox("Duration", ["45 mins", "60 mins", "90 mins", "120 mins"], index=1, key="man_dur")
                with c_m6:
                    man_topic = st.text_input("Core Topic Taught", key="man_topic")
                    
                man_summary = st.text_area("Executive Summary of Lesson", key="man_summary")
                
                c_m7, c_m8 = st.columns(2)
                with c_m7:
                    man_curriculum = st.text_area("Curriculum & Key Concepts (One per line)", key="man_curr")
                with c_m8:
                    man_hw = st.text_area("Homework Assigned & Review Notes", key="man_hw")
                    
                c_m9, c_m10 = st.columns(2)
                with c_m9:
                    man_interaction = st.text_area("Student Interaction, Engagement & Comprehension", key="man_inter")
                with c_m10:
                    man_teacher_eng = st.text_area("Teacher Notes & Constructive Feedback", key="man_t_eng")
                    
                if st.form_submit_button("💾 Save Class Report"):
                    if not man_topic:
                        st.warning("Please provide at least a topic name.")
                    else:
                        new_rep = {
                            "Report ID": str(uuid.uuid4()),
                            "Session ID": "",
                            "Date": str(man_date),
                            "Student Name": man_st,
                            "Teacher Name": man_t,
                            "Subject": man_subj,
                            "Topic": man_topic,
                            "Duration": man_dur,
                            "Executive Summary": man_summary,
                            "Curriculum Breakdown": {"topicTaught": man_topic, "keyConcepts": [c.strip() for c in man_curriculum.split("\n") if c.strip()]},
                            "Homework Tracking": {"newHomeworkDetails": man_hw, "previousHomeworkReviewed": True},
                            "Student Interaction": {"comprehensionAssessment": man_interaction, "engagementLevel": "High"},
                            "Teacher Engagement": {"encouragementAndPraise": man_teacher_eng},
                            "Anomalies": {},
                            "Social Highlights": {},
                            "File Name": f"manual_{man_st}_{man_date}",
                            "Status": "Manually Logged"
                        }
                        succ, msg = utils.save_class_report(client, new_rep)
                        if succ:
                            st.success("✅ Manual class report logged successfully!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"Failed to save: {msg}")

        # List reports
        if filtered_reps.empty:
            st.info("ℹ️ No class reports found matching the criteria. Click 'Sync with Recording Bot' or 'Add Manual Class Report' above.")
        else:
            st.write(f"Showing **{len(filtered_reps)}** class reports:")
            for idx, r_row in filtered_reps.iterrows():
                r_id = r_row.get("Report ID", "")
                r_date = r_row.get("Date", "")
                r_st = r_row.get("Student Name", "Student")
                r_t = r_row.get("Teacher Name", "Teacher")
                r_subj = r_row.get("Subject", "")
                r_top = r_row.get("Topic", "Class Session")
                r_dur = r_row.get("Duration", "60 mins")
                r_status = r_row.get("Status", "Generated")
                r_file = r_row.get("File Name", "")
                
                with st.expander(f"📅 {r_date} • 🎓 {r_st} • 📚 {r_subj}: {r_top} ({r_dur})", expanded=(idx == 0 and len(filtered_reps) == 1)):
                    st.markdown(f"**Teacher:** `{r_t}` &nbsp;•&nbsp; **Status:** `{r_status}` &nbsp;•&nbsp; **Source File:** `{r_file or 'Bot Recording'}`")
                    
                    st.info(f"**Executive Summary:** {r_row.get('Executive Summary', 'No summary recorded.')}")
                    
                    # 2-column breakdown
                    col_det1, col_det2 = st.columns(2)
                    with col_det1:
                        st.markdown("##### 📚 Curriculum Breakdown")
                        curr_data = utils._safe_json_loads(r_row.get("Curriculum Breakdown"))
                        if isinstance(curr_data, dict):
                            st.write(f"**Topic Taught:** {curr_data.get('topicTaught', r_top)}")
                            if curr_data.get("keyConcepts"):
                                st.write("**Key Concepts:**")
                                for kc in curr_data.get("keyConcepts", []):
                                    st.write(f"- {kc}")
                            if curr_data.get("learningObjectives"):
                                st.write(f"**Objectives:** {', '.join(curr_data.get('learningObjectives', []))}")
                        else:
                            st.write(curr_data)
                            
                    with col_det2:
                        st.markdown("##### 📝 Homework Tracking")
                        hw_data = utils._safe_json_loads(r_row.get("Homework Tracking"))
                        if isinstance(hw_data, dict):
                            st.write(f"**Prior Homework Reviewed:** {'Yes' if hw_data.get('previousHomeworkReviewed') else 'No / Not Set'}")
                            if hw_data.get("previousHomeworkFindings"):
                                st.write(f"**Findings:** {hw_data.get('previousHomeworkFindings')}")
                            if hw_data.get("newHomeworkDetails"):
                                st.write(f"**New Tasks Assigned:** {hw_data.get('newHomeworkDetails')}")
                        else:
                            st.write(hw_data)
                            
                    col_det3, col_det4 = st.columns(2)
                    with col_det3:
                        st.markdown("##### 🎯 Student Interaction & Comprehension")
                        inter_data = utils._safe_json_loads(r_row.get("Student Interaction"))
                        if isinstance(inter_data, dict):
                            st.write(f"**Engagement Level:** `{inter_data.get('engagementLevel', 'High')}`")
                            st.write(f"**Confidence:** `{inter_data.get('studentConfidence', 'Good')}`")
                            st.write(f"**Comprehension Notes:** {inter_data.get('comprehensionAssessment', 'N/A')}")
                        else:
                            st.write(inter_data)
                            
                    with col_det4:
                        st.markdown("##### 👨‍🏫 Teacher Feedback & Pedagogy")
                        t_data = utils._safe_json_loads(r_row.get("Teacher Engagement"))
                        if isinstance(t_data, dict):
                            st.write(f"**Methodology:** {t_data.get('pedagogyMethodology', 'Direct Instruction & Practice')}")
                            st.write(f"**Praise & Encouragement:** {t_data.get('encouragementAndPraise', 'N/A')}")
                            tb = t_data.get("timeBreakdown", {})
                            if tb:
                                st.caption(f"⏱️ Time: Instruction {tb.get('instructionPercentage', 40)}% | Practice {tb.get('practicePercentage', 40)}% | Discussion {tb.get('discussionPercentage', 20)}%")
                        else:
                            st.write(t_data)
                            
                    # Edit mode
                    with st.expander(f"✏️ Edit Report for {r_st} ({r_date})", expanded=False):
                        with st.form(f"edit_rep_form_{r_id}_{idx}"):
                            edit_topic = st.text_input("Topic", value=r_top, key=f"ed_top_{r_id}")
                            edit_exec = st.text_area("Executive Summary", value=r_row.get("Executive Summary", ""), key=f"ed_exec_{r_id}")
                            edit_t_notes = st.text_area("Teacher Remarks & Feedback", value=str(utils._safe_json_loads(r_row.get("Teacher Engagement")).get("encouragementAndPraise", "")), key=f"ed_t_notes_{r_id}")
                            edit_hw_notes = st.text_area("Homework Details", value=str(utils._safe_json_loads(r_row.get("Homework Tracking")).get("newHomeworkDetails", "")), key=f"ed_hw_notes_{r_id}")
                            
                            if st.form_submit_button("💾 Save Report Edits"):
                                rep_dict = r_row.to_dict()
                                rep_dict["Topic"] = edit_topic
                                rep_dict["Executive Summary"] = edit_exec
                                
                                # Update JSONs
                                h_dict = utils._safe_json_loads(rep_dict.get("Homework Tracking"))
                                if isinstance(h_dict, dict):
                                    h_dict["newHomeworkDetails"] = edit_hw_notes
                                    rep_dict["Homework Tracking"] = h_dict
                                    
                                t_dict = utils._safe_json_loads(rep_dict.get("Teacher Engagement"))
                                if isinstance(t_dict, dict):
                                    t_dict["encouragementAndPraise"] = edit_t_notes
                                    rep_dict["Teacher Engagement"] = t_dict
                                    
                                rep_dict["Status"] = "Edited"
                                succ, msg = utils.save_class_report(client, rep_dict)
                                if succ:
                                    st.success("✅ Changes saved to Google Sheet!")
                                    time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error(f"Save failed: {msg}")

    # ========================================================
    # SUBTAB 2: CONSOLIDATED MONTHLY REPORTS & SIGN-OFF
    # ========================================================
    with subtab_monthly:
        st.subheader("Monthly Academic Evaluation & 2-Stage Sign-off")
        st.caption("Consolidates all session reports for a student across the month. Must be confirmed by the Teacher, approved by the Head Teacher, and then exported for parents.")

        # Controls
        st_list_for_monthly = [s for s in df_students_all["Student Name"].dropna().unique() if str(s).strip()] if not df_students_all.empty else ["Student"]
        curr_month = datetime.date.today().strftime("%B %Y")
        month_choices = [curr_month, "September 2026", "November 2026", "December 2026"]
        
        c_m_sel1, c_m_sel2, c_m_sel3 = st.columns([2, 2, 2])
        with c_m_sel1:
            sel_m_student = st.selectbox("Select Student", st_list_for_monthly, key="m_sel_student")
        with c_m_sel2:
            sel_m_month = st.selectbox("Select Month", month_choices, key="m_sel_month")
        with c_m_sel3:
            st.markdown("<br>", unsafe_allow_html=True)
            btn_gen_monthly = st.button("⚡ Generate / Refresh Monthly Draft", key="btn_gen_monthly")

        if btn_gen_monthly and sel_m_student:
            draft = utils.generate_monthly_report_draft(client, sel_m_student, sel_m_month)
            succ, msg = utils.save_monthly_report(client, draft)
            if succ:
                st.success(f"✅ Generated monthly report draft for {sel_m_student} ({sel_m_month}) from recorded sessions!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"Error generating draft: {msg}")

        # Look up existing monthly report for this student and month
        s_norm = utils.normalize_name(sel_m_student)
        curr_report_match = pd.DataFrame()
        if not df_monthly_reps.empty and "Student Name" in df_monthly_reps.columns:
            curr_report_match = df_monthly_reps[
                (df_monthly_reps["Student Name"].apply(utils.normalize_name) == s_norm) &
                (df_monthly_reps["Month"].str.strip().str.lower() == sel_m_month.strip().lower())
            ]

        if curr_report_match.empty:
            st.info(f"ℹ️ No monthly report on file for **{sel_m_student}** for **{sel_m_month}** yet. Click '⚡ Generate / Refresh Monthly Draft' above to aggregate their class reports into a monthly report.")
        else:
            rep_data = curr_report_match.iloc[0].to_dict()
            rep_id = rep_data.get("Monthly Report ID")
            rep_status = rep_data.get("Status", "Draft")
            
            # Workflow Status Badge Banner
            if rep_status == "Approved by Head Teacher":
                st.success("🟢 **Status: Approved by Head Teacher** • This monthly report is fully verified and ready for the parent!")
            elif rep_status == "Confirmed by Teacher":
                st.info("🔵 **Status: Confirmed by Teacher** • Awaiting final quality approval from the Head Teacher.")
            else:
                st.warning("🟡 **Status: Draft (Pending Teacher Confirmation)** • Please review and confirm below.")

            # Summary Metrics Row
            cm_c1, cm_c2, cm_c3, cm_c4 = st.columns(4)
            cm_c1.metric("Classes Held", rep_data.get("Total Classes", 0))
            cm_c2.metric("Tutoring Hours", f"{rep_data.get('Total Hours', 0)}h")
            cm_c3.metric("Lead Teacher", rep_data.get("Teacher Name", "Tutor"))
            cm_c4.metric("Subject", rep_data.get("Subject", "General"))

            # Editable Monthly Report Form
            with st.form(f"monthly_edit_form_{rep_id}"):
                st.markdown("### ✏️ Edit Monthly Evaluation Details")
                st.caption("You can edit any section before confirming or approving. Edits are saved directly to Google Sheets.")
                
                f_curriculum = st.text_area("1. Curriculum & Topics Covered Across Month", value=rep_data.get("Curriculum Covered", ""), height=120)
                f_hw = st.text_area("2. Homework & Independent Practice Performance", value=rep_data.get("Homework Rating", ""), height=90)
                f_comp = st.text_area("3. Concept Comprehension & Academic Growth", value=rep_data.get("Comprehension & Progress", ""), height=90)
                f_teacher_rem = st.text_area("4. Teacher's Evaluation & Remarks", value=rep_data.get("Teacher Remarks", ""), height=100)
                f_ht_recs = st.text_area("5. Head Teacher's Quality Seal & Recommendations", value=rep_data.get("Head Teacher Recommendations", ""), height=90)
                
                c_btn_save, c_btn_t_confirm, c_btn_ht_approve = st.columns(3)
                with c_btn_save:
                    btn_save_edits = st.form_submit_button("💾 Save Changes to Report")
                with c_btn_t_confirm:
                    btn_t_confirm = st.form_submit_button("✍️ Teacher Confirm & Sign-off")
                with c_btn_ht_approve:
                    btn_ht_approve = st.form_submit_button("👑 Head Teacher Final Approval")

                if btn_save_edits:
                    rep_data["Curriculum Covered"] = f_curriculum
                    rep_data["Homework Rating"] = f_hw
                    rep_data["Comprehension & Progress"] = f_comp
                    rep_data["Teacher Remarks"] = f_teacher_rem
                    rep_data["Head Teacher Recommendations"] = f_ht_recs
                    succ, msg = utils.save_monthly_report(client, rep_data)
                    if succ:
                        st.success("✅ Monthly report changes saved successfully!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"Save failed: {msg}")

                if btn_t_confirm:
                    t_signer = rep_data.get("Teacher Name") or "Teacher"
                    succ, msg = utils.confirm_monthly_report_teacher(client, rep_id, t_signer, f_teacher_rem)
                    if succ:
                        st.balloons()
                        st.success("✅ Monthly report confirmed by Teacher! Submitted to Head Teacher.")
                        time.sleep(0.7)
                        st.rerun()
                    else:
                        st.error(f"Confirmation failed: {msg}")

                if btn_ht_approve:
                    succ, msg = utils.approve_monthly_report_head_teacher(client, rep_id, "Head Teacher", f_ht_recs)
                    if succ:
                        st.balloons()
                        st.success("🎉 Monthly report approved by Head Teacher! Ready to export for parent.")
                        time.sleep(0.7)
                        st.rerun()
                    else:
                        st.error(f"Approval failed: {msg}")

            # Download & Preview Section
            st.markdown("---")
            st.subheader("📥 Export & Download Report for Parent")
            st.caption("Generate a high-resolution, printable HTML/PDF evaluation report formatted with Pinnacle Academic Services branding.")
            
            html_parent_report = utils.generate_monthly_report_html(rep_data)
            
            cdl1, cdl2 = st.columns([1, 2])
            with cdl1:
                st.download_button(
                    label="📄 Download Printable Report (HTML / PDF)",
                    data=html_parent_report,
                    file_name=f"PAS_Monthly_Evaluation_{sel_m_student}_{sel_m_month}.html",
                    mime="text/html",
                    key=f"dl_parent_m_{rep_id}"
                )
            with cdl2:
                st.caption("💡 **Tip:** Open the downloaded HTML file in Chrome/Edge and press `Ctrl+P` (or click the print button) to save as an official PDF to send to the parent.")

            with st.expander("👁️ Preview Parent-Facing Report", expanded=False):
                st.components.v1.html(html_parent_report, height=750, scrolling=True)

# --- ADMIN DASHBOARD ---
elif tab == "Admin Dashboard":
    st.header("📊 Admin Dashboard")
    
    # --- HEAD TEACHER MONTHLY REPORTS APPROVAL QUEUE ---
    df_m_all = utils.get_monthly_reports_data(client)
    if not df_m_all.empty and "Status" in df_m_all.columns:
        pending_ht_reports = df_m_all[df_m_all["Status"] == "Confirmed by Teacher"]
        if not pending_ht_reports.empty:
            st.info(f"🔔 **Attention Head Teacher:** There are **{len(pending_ht_reports)}** monthly report(s) confirmed by teachers awaiting your final quality approval.")
            with st.expander(f"👑 Review Pending Monthly Reports ({len(pending_ht_reports)} pending)", expanded=True):
                for _, p_rep in pending_ht_reports.iterrows():
                    p_st = p_rep.get("Student Name")
                    p_mo = p_rep.get("Month")
                    p_t = p_rep.get("Teacher Name")
                    p_id = p_rep.get("Monthly Report ID")
                    
                    st.markdown(f"**Student:** `{p_st}` &nbsp;•&nbsp; **Month:** `{p_mo}` &nbsp;•&nbsp; **Teacher:** `{p_t}`")
                    st.write(f"**Teacher Remarks:** {p_rep.get('Teacher Remarks')}")
                    
                    c_app1, c_app2 = st.columns([1, 1])
                    with c_app1:
                        if st.button(f"👑 Approve & Finalize Report for {p_st}", key=f"ht_q_app_{p_id}"):
                            succ, msg = utils.approve_monthly_report_head_teacher(client, p_id, "Head Teacher")
                            if succ:
                                st.success(f"✅ Approved monthly report for {p_st}!")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(f"Error: {msg}")
                    with c_app2:
                        html_q = utils.generate_monthly_report_html(p_rep.to_dict())
                        st.download_button(
                            label=f"📥 Download Report for {p_st}",
                            data=html_q,
                            file_name=f"PAS_Report_{p_st}_{p_mo}.html",
                            mime="text/html",
                            key=f"ht_q_dl_{p_id}"
                        )
                    st.markdown("---")

    
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
    # REF: Replaced with student-centric schedule generation (Phase 2 Refactor)
    
    # 1. Validation / Data Health Check
    with st.expander("🛠️ Data Integrity Check (Click to view errors)"):
        df_issues = utils.validate_data_integrity(client)
        if not df_issues.empty:
            st.error(f"Found {len(df_issues)} formatting issues in your Google Sheet.")
            st.dataframe(df_issues, use_container_width=True)
            st.caption("Please fix these in the Google Sheet (Students 'Class Times' or Teachers 'Schedule').")
        else:
            st.success("✅ Data looks good! No formatting errors found.")

    # 2. Generate Schedule
    if selected_day_view:
        df_agenda = utils.generate_master_schedule(client, selected_day_full=selected_day_view)
        
        if not df_agenda.empty:
            st.dataframe(df_agenda, use_container_width=True, hide_index=True)
        else:
            st.info(f"No classes scheduled for {selected_day_view}.")
    
    st.markdown("---")

    df_students = utils.get_students_data(client)
    
    if not df_students.empty:
        # Row 1: Charts & Billing Data
        st.subheader("💰 Billing & Financials")
        
        # 1. Billing Overview Table
        df_balances = utils.get_all_student_balances(client)
        if not df_balances.empty:
            # MEtrics
            total_rev = df_balances["Total Owed"].sum()
            total_classes = df_balances["Classes Count"].sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Revenue Expected", f"NGN {total_rev:,.2f}")
            m2.metric("Total Classes Taught", f"{int(total_classes)}")
            m3.metric("Number of Students", len(df_balances))
            
            with st.expander("View Detailed Billing Report", expanded=True):
                st.dataframe(df_balances, use_container_width=True)
        else:
            st.info("No billing data computed.")
            
        st.markdown("---")
        st.subheader("Financial Overview (Payment Status)")
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
                standard_subjects = utils.STANDARD_SUBJECTS
                
                if sel_s_edit and not df_students.empty and "Student Name" in df_students.columns:
                    # Get current data - Find row where Student Name matches
                    curr_s = df_students[df_students["Student Name"] == sel_s_edit].iloc[0]
                    
                    with st.container():
                        # Use .get with defaults. keys match exact sheet headers usually.
                        
                        es_name = st.text_input("Name", curr_s.get("Student Name", ""), help="Changing name will update Billing profile too.")
                        es_email = st.text_input("Email", curr_s.get("Email", "")) # or "Email Address"?
                        es_phone = st.text_input("Phone", curr_s.get("Phone", "")) # or "Phone Number"?
                        
                        curr_times_str = str(curr_s.get("Class Times", ""))
                        
                        if "edit_student_name" not in st.session_state or st.session_state.edit_student_name != sel_s_edit:
                            st.session_state.edit_student_name = sel_s_edit
                            parsed_classes = utils.parse_student_schedule(curr_times_str)
                            valid_classes = [c for c in parsed_classes if c.get("Valid")]
                            st.session_state.edit_subject_rows = max(1, len(valid_classes))
                            st.session_state.edit_class_data = valid_classes
                            
                        st.markdown("### Subjects & Class Times")
                        day_options = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                        
                        df_teachers_list = utils.get_teacher_data(client)
                        teacher_options = ["Unassigned"]
                        if not df_teachers_list.empty and "Teacher Name" in df_teachers_list.columns:
                            teacher_options.extend(df_teachers_list["Teacher Name"].tolist())
                            
                        # Find current assigned teachers for THIS student using normalize_name
                        curr_student_norm = utils.normalize_name(sel_s_edit)
                        current_teachers_mapped = []
                        if not df_teachers_list.empty:
                            for _, t_row in df_teachers_list.iterrows():
                                assigned = str(t_row.get("Assigned Students", ""))
                                assigned_norms = [utils.normalize_name(a) for a in assigned.split(",") if a.strip()]
                                if curr_student_norm in assigned_norms:
                                    current_teachers_mapped.append(t_row.get("Teacher Name"))
                        
                        all_edit_subjects = []
                        
                        for i in range(st.session_state.edit_subject_rows):
                            # Try to get defaults if they exist
                            def_sub = standard_subjects[0]
                            def_teacher = current_teachers_mapped[0] if current_teachers_mapped else "Unassigned"
                            def_day = "Monday"
                            def_start = datetime.time(9, 0)
                            def_end = datetime.time(10, 0)
                            
                            if i < len(st.session_state.edit_class_data):
                                c_data = st.session_state.edit_class_data[i]
                                if c_data.get("Subject") in standard_subjects:
                                    def_sub = c_data["Subject"]
                                if c_data.get("Day") in day_options:
                                    def_day = c_data["Day"]
                                if c_data.get("TimeObj"):
                                    def_start = c_data["TimeObj"]
                                if c_data.get("EndTime") and c_data.get("EndTime") != "-":
                                    try:
                                        def_end = datetime.datetime.strptime(c_data["EndTime"], "%I:%M %p").time()
                                    except:
                                        pass
                                if c_data.get("AssignedTeacher") in teacher_options:
                                    def_teacher = c_data["AssignedTeacher"]
                            
                            c1, c2, c3, c4, c5, c6 = st.columns([3, 3, 2, 2, 2, 1])
                            with c1:
                                sub = st.selectbox(f"Subject {i+1}", standard_subjects, index=standard_subjects.index(def_sub) if def_sub in standard_subjects else 0, key=f"esub_{sel_s_edit}_{i}")
                            with c2:
                                tcher = st.selectbox(f"Teacher {i+1}", teacher_options, index=teacher_options.index(def_teacher) if def_teacher in teacher_options else 0, key=f"eteach_{sel_s_edit}_{i}")
                            with c3:
                                day = st.selectbox(f"Day {i+1}", day_options, index=day_options.index(def_day) if def_day in day_options else 0, key=f"eday_{sel_s_edit}_{i}")
                            with c4:
                                start_t = st.time_input(f"Start {i+1}", value=def_start, key=f"estart_{sel_s_edit}_{i}")
                            with c5:
                                end_t = st.time_input(f"End {i+1}", value=def_end, key=f"eend_{sel_s_edit}_{i}")
                            with c6:
                                st.markdown("<br>", unsafe_allow_html=True)
                                is_deleted = st.checkbox("🗑️", key=f"edel_{sel_s_edit}_{i}")
                            
                            if not is_deleted:
                                all_edit_subjects.append({
                                    "Subject": sub,
                                    "Teacher": tcher,
                                    "Day": day,
                                    "StartTime": start_t,
                                    "EndTime": end_t
                                })
                            
                        def add_edit_subject_row():
                            st.session_state.edit_subject_rows += 1
                            
                        st.button("+ Add Another Subject", on_click=add_edit_subject_row, key="add_esub_btn")
                        
                        # Rebuild subjects & times strings
                        es_subj_list = list(set([entry["Subject"] for entry in all_edit_subjects]))
                        es_subj = ", ".join(es_subj_list)
                        
                        selected_teachers = list(set([entry["Teacher"] for entry in all_edit_subjects if entry["Teacher"] != "Unassigned"]))
                        
                        class_times_parts = []
                        for entry in all_edit_subjects:
                            s_str = entry["StartTime"].strftime("%I:%M %p")
                            e_str = entry["EndTime"].strftime("%I:%M %p")
                            teacher_str = f" [{entry['Teacher']}]" if entry.get('Teacher') and entry['Teacher'] != "Unassigned" else ""
                            class_times_parts.append(f"{entry['Subject']} ({entry['Day'][:3]} {s_str} - {e_str}){teacher_str}")
                            
                        es_times = ", ".join(class_times_parts)
                        
                        st.markdown("---")
                        col_update, col_delete = st.columns(2)
                        
                        with col_update:
                            if st.button("Update Student", key="submit_edit_student"):
                                success, msg = utils.update_student(client, sel_s_edit, {
                                    "Name": es_name,
                                    "Email": es_email,
                                    "Phone": es_phone,
                                    "Subjects": es_subj,
                                    "Class Times": es_times,
                                    "Selected Teachers": selected_teachers
                                })
                                if success: 
                                    st.success(msg)
                                    time.sleep(1)
                                    st.rerun()
                                else: 
                                    st.error(msg)
                                    
                        with col_delete:
                            if st.button("Delete Student", key="delete_s_btn", type="primary"):
                                success, msg = utils.delete_student(client, sel_s_edit)
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
                    
                    t_portal_link = get_teacher_portal_link(sel_t_edit)
                    st.info(f"🔗 **Dedicated Portal Link for {sel_t_edit}:**")
                    st.code(t_portal_link, language="text")
                    st.caption("Send this link to the teacher. They will only see their assigned students and cannot access the admin dashboard.")
                    
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
                        
                        # Robust matching using normalize_name so spaces don't drop students
                        student_norm_map = {utils.normalize_name(s): s for s in valid_students_list}
                        valid_defaults = []
                        for x in curr_assign_list:
                            x_norm = utils.normalize_name(x)
                            if x_norm in student_norm_map:
                                valid_defaults.append(student_norm_map[x_norm])
                            elif x in valid_students_list:
                                valid_defaults.append(x)
                        
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
                                is_checked = st.checkbox(day, value=is_active, key=f"et_d_{sel_t_edit}_{day}")
                            
                            if is_checked:
                                # Default times or parsed times
                                def_start, def_end = parsed_sched.get(day, (datetime.time(9,0), datetime.time(17,0)))
                                
                                with col2:
                                    start_time = st.time_input(f"Start ({day})", value=def_start, key=f"et_s_{sel_t_edit}_{day}")
                                with col3:
                                    end_time = st.time_input(f"End ({day})", value=def_end, key=f"et_e_{sel_t_edit}_{day}")
                                
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
                
                monthly_fee = st.number_input("Teacher Monthly Fee (NGN)", min_value=0.0, step=5000.0, value=20000.0, key="pay_t_fee")
                
                if st.button("Calculate Pay & Generate Report"):
                    count, total_revenue, teacher_pay, df_breakdown = utils.calculate_teacher_pay(client, selected_t, monthly_fee)
                    
                    teacher_row = df_teachers[df_teachers["Teacher Name"] == selected_t].iloc[0]
                    schedule_str = str(teacher_row.get("Class Schedule", ""))
                    estimated_classes = utils.estimate_monthly_classes(schedule_str)
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.info(f"Classes Taught: {count}")
                        st.metric("Total Revenue Generated", f"NGN {total_revenue:,.2f}")
                        st.success(f"💰 Teacher Pay: NGN {teacher_pay:,.2f}")
                    
                    with c2:
                        st.info(f"Projected Monthly Classes: {estimated_classes}")
                        st.caption("Based on the teacher's current weekly class schedule.")
                    
                    if not df_breakdown.empty:
                        st.markdown("#### Teacher Revenue Breakdown")
                        st.caption("Shows how much revenue each of this teacher's students brought in based on actual classes taught (from Reviews tab).")
                        # Format currencies in dataframe
                        df_display = df_breakdown.copy()
                        if "Student Rate (NGN)" in df_display.columns:
                            df_display["Student Rate (NGN)"] = df_display["Student Rate (NGN)"].apply(lambda x: f"NGN {float(x):,.2f}" if pd.notnull(x) else "NGN 0.00")
                        if "Revenue Generated (NGN)" in df_display.columns:
                            df_display["Revenue Generated (NGN)"] = df_display["Revenue Generated (NGN)"].apply(lambda x: f"NGN {float(x):,.2f}" if pd.notnull(x) else "NGN 0.00")
                            
                        st.dataframe(df_display, use_container_width=True, hide_index=True)
                    else:
                        st.info("No classes recorded for this teacher yet.")
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

        # Row 4.5: Teacher Portals & Weekly Confirmations
        st.subheader("📋 Teacher Portals & Weekly Confirmations")
        with st.expander("Teacher Links & Weekly Lesson Confirmations", expanded=False):
            df_t_overview = utils.get_teacher_data(client)
            if not df_t_overview.empty and "Teacher Name" in df_t_overview.columns:
                st.markdown("##### 🔗 Teacher Portal Access Links")
                st.caption("Each link provides isolated access for that specific teacher. They only see their assigned students.")
                portal_records = []
                for _, tr in df_t_overview.iterrows():
                    tn = tr.get("Teacher Name", "")
                    assigned = tr.get("Assigned Students", "")
                    link = get_teacher_portal_link(tn)
                    portal_records.append({
                        "Teacher Name": tn,
                        "Assigned Students": assigned,
                        "Portal Link": link
                    })
                st.dataframe(pd.DataFrame(portal_records), use_container_width=True, hide_index=True)
            
            st.markdown("##### 📅 Weekly Confirmations & Lesson Plans")
            df_plans_overview = utils.get_weekly_plans_data(client)
            if not df_plans_overview.empty:
                st.dataframe(df_plans_overview, use_container_width=True, hide_index=True)
            else:
                st.info("No weekly plans or confirmations recorded yet.")

        # Row 5: Schedule Manager (New - Session System)
        st.subheader("📅 Schedule Manager")
        with st.expander("Schedule a New Class"):
            st.write("Create a session for the new Check-in System.")
            # Dropdowns
            teachers_list = df_teachers["Teacher Name"].tolist() if not df_teachers.empty and "Teacher Name" in df_teachers.columns else []
            students_list = df_students["Student Name"].tolist() if not df_students.empty else []
            
            with st.form("schedule_form"):
                sc_teacher = st.selectbox("Teacher", teachers_list)
                sc_students = st.multiselect("Students", students_list)
                
                # Subject Dropdown (Standard + Other)
                subject_opts = utils.STANDARD_SUBJECTS
                sc_subject = st.selectbox("Subject", subject_opts)
                if sc_subject == "Other":
                    sc_subject = st.text_input("Enter Subject")
                
                sc_link = st.text_input("Meeting Link (Leave blank to auto-generate Google Meet)")
                
                c1, c2, c3 = st.columns(3)
                sc_date = c1.date_input("Date")
                sc_time = c2.time_input("Start Time")
                sc_duration = c3.selectbox("Duration", ["1 Hour", "30 Mins", "45 Mins", "1.5 Hours", "2 Hours"])
                
                if st.form_submit_button("Schedule & Send Invite"):
                    if not sc_students:
                        st.error("Please select at least one student.")
                    else:
                        dt_str = f"{sc_date} {sc_time}"
                        
                        # Unpack 3 values now: Success, Msg, SessionID
                        success, msg, session_id_res = utils.schedule_class(client, sc_teacher, sc_students, sc_subject, dt_str, sc_duration, sc_link)
                    
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

import streamlit as st
import psycopg2
import psycopg2.extras
import hashlib
import json
import urllib.request
import urllib.parse
import os
from datetime import datetime, date, timedelta

st.set_page_config(page_title="VendorsLink", page_icon="V", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.main-title{font-size:2.4rem;font-weight:800;color:#1a73e8;text-align:center}
.sub-title{font-size:1.1rem;color:#666;text-align:center;margin-bottom:1.5rem}
.card{background:#f8f9fa;border-radius:10px;padding:1rem 1.2rem;margin-bottom:.8rem}
.card-vendor{border-left:4px solid #1a73e8}
.card-worker{border-left:4px solid #28a745}
.job-card{background:#ffffff;border-radius:12px;padding:1.2rem 1.4rem;margin-bottom:1rem;border:1px solid #e0e0e0;box-shadow:0 2px 6px rgba(0,0,0,0.06)}
.job-title{font-size:1.2rem;font-weight:700;color:#1a73e8;margin-bottom:0.2rem}
.job-meta{font-size:0.85rem;color:#888;margin-bottom:0.5rem}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:0.78rem;font-weight:600;margin-right:4px}
.badge-open{background:#e6f4ea;color:#1e7e34}
.badge-review{background:#fff3e0;color:#e65100}
.badge-closed{background:#fce8e6;color:#c0392b}
.badge-cat{background:#e8f0fe;color:#1a73e8}
.ai-card{background:linear-gradient(135deg,#e8f0fe,#f0f4ff);border-radius:14px;padding:1.3rem 1.5rem;margin-bottom:1rem;border:1px solid #c5d4f5}
.ai-rank{font-size:1.8rem;font-weight:900;color:#1a73e8}
.ai-name{font-size:1.1rem;font-weight:700;color:#222}
.ai-score{font-size:1rem;font-weight:600;color:#1e7e34}
.ai-reason{font-size:0.92rem;color:#444;margin-top:0.4rem}
.ai-hero{background:linear-gradient(135deg,#1a73e8,#0d47a1);color:white;border-radius:14px;padding:1.2rem 1.6rem;margin-bottom:1.2rem}
.popup-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center}
</style>
""", unsafe_allow_html=True)

DB = "vendorslink.db"

def get_conn():
    db_url = ""
    try:
        db_url = st.secrets["DATABASE_URL"]
    except Exception:
        pass
    if not db_url:
        db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        st.error("DATABASE_URL not set. Add it to Streamlit secrets or environment.")
        st.stop()
    conn = psycopg2.connect(db_url, sslmode="require")
    conn.autocommit = False
    return conn

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def today():
    return date.today().strftime("%Y-%m-%d")

def hp(p):
    return hashlib.sha256(p.strip().encode()).hexdigest()

def init_db():
    c = get_conn()
    cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        name TEXT, email TEXT UNIQUE,
        password TEXT, role TEXT,
        phone TEXT, location TEXT,
        created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id SERIAL PRIMARY KEY,
        vendor_id INTEGER, title TEXT,
        description TEXT, location TEXT,
        salary TEXT, category TEXT,
        date_posted TEXT, deadline TEXT,
        months INTEGER DEFAULT 1,
        is_closed INTEGER DEFAULT 0,
        status TEXT DEFAULT 'accepting',
        hired_worker_id INTEGER DEFAULT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS applications(
        id SERIAL PRIMARY KEY,
        job_id INTEGER, worker_id INTEGER,
        status TEXT DEFAULT 'Pending',
        message TEXT, date_applied TEXT)""")
    c.commit()
    c.close()

init_db()

def auto_close_expired_jobs():
    c = get_conn()
    cur = c.cursor()
    cur.execute("UPDATE jobs SET is_closed=1 WHERE deadline < %s AND is_closed=0", (today(),))
    c.commit()
    c.close()

auto_close_expired_jobs()

for k, v in [("logged_in",False),("user_id",None),("user_name",""),
             ("user_role",""),("user_email",""),("user_location",""),
             ("selected_job",None),("ai_result",None),
             ("show_reg_popup",False),("show_hire_popup",False),
             ("show_apply_popup",False),("show_job_popup",False),
             ("hired_worker_name",""),("popup_msg",""),
             ("job_popup_msg",""),("nav_page","Home")]:
    if k not in st.session_state:
        st.session_state[k] = v

CATS = ["Construction","Cleaning","Delivery","IT","Healthcare","Education","Retail","Other"]

# ============================================================
# POPUP SYSTEM
# ============================================================
def show_celebration_popup(title, message, icon="star"):
    # Balloons
    st.balloons()
    # Beautiful popup using st.success with big styling
    st.markdown(f"""
    <div style="position:fixed;top:0;left:0;width:100%;height:100%;
         background:rgba(0,0,0,0.6);z-index:9999;display:flex;
         align-items:center;justify-content:center;">
      <div style="background:white;border-radius:20px;padding:2.5rem 3rem;
           max-width:480px;width:90%;text-align:center;
           box-shadow:0 20px 60px rgba(0,0,0,0.3);
           animation:popIn 0.4s ease;">
        <div style="font-size:3.5rem;margin-bottom:0.5rem">&#127881;</div>
        <h2 style="color:#1a73e8;margin:0.3rem 0">{title}</h2>
        <p style="color:#555;font-size:1rem;margin:0.8rem 0 1.5rem 0">{message}</p>
        <div style="font-size:1.8rem">&#127881; &#11088; &#127881;</div>
      </div>
    </div>
    <style>
    @keyframes popIn {{
      0%{{transform:scale(0.5);opacity:0}}
      70%{{transform:scale(1.05)}}
      100%{{transform:scale(1);opacity:1}}
    }}
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# DB FUNCTIONS
# ============================================================

def register(name, email, pw, cpw, role, phone, location):
    if not all([name.strip(), email.strip(), pw, cpw, role]):
        return False, "Please fill all required fields."
    if pw != cpw:
        return False, "Passwords do not match."
    if len(pw) < 4:
        return False, "Password must be at least 4 characters."
    c = get_conn()
    cur = c.cursor()
    try:
        cur.execute("INSERT INTO users(name,email,password,role,phone,location,created_at)VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (name.strip(), email.lower(), hp(pw), role, phone, location.strip(), now()))
        c.commit()
        return True, f"Registered as {role} successfully!"
    except psycopg2.errors.UniqueViolation:
        return False, "Email already registered."
    finally:
        c.close()

def login(email, pw, role):
    c = get_conn()
    cur = c.cursor()
    cur.execute("SELECT id,name,role,email,location FROM users WHERE email=%s AND password=%s AND role=%s",
        (email.lower(), hp(pw), role))
    u = cur.fetchone()
    c.close()
    return u

def vendor_already_posted(vid, title):
    c = get_conn()
    cur = c.cursor()
    cur.execute("SELECT id FROM jobs WHERE vendor_id=%s AND LOWER(title)=LOWER(%s)", (vid, title.strip()))
    r = cur.fetchone()
    c.close()
    return r is not None

def post_job(vid, title, desc, loc, sal, cat, months):
    deadline = (date.today() + timedelta(days=months*30)).strftime("%Y-%m-%d")
    c = get_conn()
    cur = c.cursor()
    cur.execute("INSERT INTO jobs(vendor_id,title,description,location,salary,category,date_posted,deadline,months,is_closed,status)VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,0,'accepting')",
        (vid, title, desc, loc, sal, cat, now(), deadline, months))
    c.commit()
    c.close()

def vendor_jobs(vid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("""SELECT j.id,j.title,j.location,j.salary,j.category,j.date_posted,j.deadline,j.months,j.is_closed,j.status,
        COUNT(a.id) as app_count
        FROM jobs j LEFT JOIN applications a ON a.job_id=j.id
        WHERE j.vendor_id=%s GROUP BY j.id,j.title,j.location,j.salary,j.category,j.date_posted,j.deadline,j.months,j.is_closed,j.status ORDER BY j.id DESC""", (vid,))
    r = cur.fetchall()
    c.close()
    return r

def set_job_status(jid, vid, status):
    c = get_conn()
    cur = c.cursor()
    cur.execute("UPDATE jobs SET status=%s WHERE id=%s AND vendor_id=%s", (status, jid, vid))
    c.commit()
    c.close()

def close_job_manually(jid, vid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("UPDATE jobs SET is_closed=1 WHERE id=%s AND vendor_id=%s", (jid, vid))
    c.commit()
    c.close()

def vendor_apps(vid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("""SELECT a.id,j.title,u.name,u.email,u.phone,a.message,a.status,a.date_applied,j.id,j.status
        FROM applications a JOIN jobs j ON a.job_id=j.id
        JOIN users u ON a.worker_id=u.id
        WHERE j.vendor_id=%s ORDER BY a.id DESC""", (vid,))
    r = cur.fetchall()
    c.close()
    return r

def get_apps_for_job(jid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("""SELECT a.id,u.name,u.location,a.message,a.date_applied,a.status,u.phone
        FROM applications a JOIN users u ON a.worker_id=u.id
        WHERE a.job_id=%s ORDER BY a.id ASC""", (jid,))
    r = cur.fetchall()
    c.close()
    return r

def get_vendor_open_jobs(vid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("SELECT id,title,description,location,category FROM jobs WHERE vendor_id=%s AND is_closed=0 ORDER BY id DESC", (vid,))
    r = cur.fetchall()
    c.close()
    return r

def hire_worker(aid, jid, vid):
    c = get_conn()
    cur = c.cursor()
    # Get worker info
    cur.execute("SELECT u.name FROM applications a JOIN users u ON a.worker_id=u.id WHERE a.id=%s", (aid,))
    row = cur.fetchone()
    worker_name = row[0] if row else "Worker"
    # Mark hired application as Accepted
    cur.execute("UPDATE applications SET status='Accepted' WHERE id=%s AND job_id IN(SELECT id FROM jobs WHERE vendor_id=%s)",
        (aid, vid))
    # Reject all other pending applications for same job
    cur.execute("UPDATE applications SET status='Rejected' WHERE job_id=%s AND id!=%s AND status='Pending'", (jid, aid))
    # Close the job
    cur.execute("UPDATE jobs SET is_closed=1, status='hired' WHERE id=%s AND vendor_id=%s", (jid, vid))
    c.commit()
    c.close()
    return worker_name

def count_active_offers(wid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM applications a JOIN jobs j ON a.job_id=j.id WHERE a.worker_id=%s AND a.status='Accepted' AND j.is_closed=0", (wid,))
    cnt = cur.fetchone()[0]
    c.close()
    return cnt

def worker_already_applied(jid, wid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("SELECT id FROM applications WHERE job_id=%s AND worker_id=%s", (jid, wid))
    r = cur.fetchone()
    c.close()
    return r is not None

def search_jobs(kw, loc, cat):
    c = get_conn()
    cur = c.cursor()
    params = [today()]
    q = """SELECT j.id,j.title,u.name,j.location,j.salary,j.category,j.description,j.date_posted,j.deadline,j.months,j.status,
        COUNT(a.id) as app_count
        FROM jobs j JOIN users u ON j.vendor_id=u.id
        LEFT JOIN applications a ON a.job_id=j.id
        WHERE j.is_closed=0 AND j.deadline >= %s"""
    if kw.strip():
        q += " AND(j.title ILIKE %s OR j.description ILIKE %s)"
        params += [f"%{kw}%", f"%{kw}%"]
    if loc.strip():
        q += " AND j.location ILIKE %s"
        params.append(f"%{loc}%")
    if cat and cat != "All":
        q += " AND j.category=%s"
        params.append(cat)
    q += " GROUP BY j.id,j.title,u.name,j.location,j.salary,j.category,j.description,j.date_posted,j.deadline,j.months,j.status ORDER BY j.id DESC"
    cur.execute(q, params)
    r = cur.fetchall()
    c.close()
    return r

def get_job_by_id(jid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("""SELECT j.id,j.title,u.name,j.location,j.salary,j.category,j.description,j.date_posted,j.deadline,j.months,j.is_closed,j.status
        FROM jobs j JOIN users u ON j.vendor_id=u.id WHERE j.id=%s""", (jid,))
    r = cur.fetchone()
    c.close()
    return r

def apply_job(jid, wid, msg):
    active = count_active_offers(wid)
    if active >= 3:
        return False, "You have 3 active job offers. Please respond to them before applying to more jobs."
    c = get_conn()
    cur = c.cursor()
    cur.execute("SELECT id,is_closed,deadline,status FROM jobs WHERE id=%s", (jid,))
    job = cur.fetchone()
    if not job:
        c.close()
        return False, "Job ID not found."
    if job[1] == 1 or job[2] < today():
        c.close()
        return False, "This job is closed."
    if job[3] == "reviewing":
        c.close()
        return False, "This job is currently reviewing applications. No new applications accepted."
    cur.execute("SELECT id FROM applications WHERE job_id=%s AND worker_id=%s", (jid, wid))
    if cur.fetchone():
        c.close()
        return False, "You already applied to this job."
    cur.execute("INSERT INTO applications(job_id,worker_id,message,status,date_applied)VALUES(%s,%s,%s,%s,%s)",
        (jid, wid, msg, "Pending", now()))
    c.commit()
    c.close()
    return True, "Application submitted successfully!"

def worker_apps(wid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("""SELECT a.id,j.title,u.name,j.location,j.salary,a.status,a.date_applied,j.is_closed,j.status
        FROM applications a JOIN jobs j ON a.job_id=j.id
        JOIN users u ON j.vendor_id=u.id
        WHERE a.worker_id=%s ORDER BY a.id DESC""", (wid,))
    r = cur.fetchall()
    c.close()
    return r

def reject_offer(aid, wid):
    c = get_conn()
    cur = c.cursor()
    cur.execute("UPDATE applications SET status='Rejected' WHERE id=%s AND worker_id=%s", (aid, wid))
    c.commit()
    c.close()

def days_left(deadline_str):
    try:
        dl = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        return (dl - date.today()).days
    except:
        return None

# ============================================================
# AI MATCHING (Gemini)
# ============================================================

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite-preview-06-17",
]

def call_gemini_api(prompt, api_key):
    import urllib.error, time
    errors = []
    for model in GEMINI_MODELS:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json"
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text, None
        except urllib.error.HTTPError as e:
            body_bytes = e.read()
            try:
                err_body = json.loads(body_bytes.decode("utf-8"))
                err_msg  = err_body.get("error", {}).get("message", str(e))
            except Exception:
                err_msg = body_bytes.decode("utf-8", errors="replace")[:200]
            if e.code == 429:
                errors.append(f"{model}: rate limit - waiting")
                time.sleep(25)
                continue
            elif e.code == 404:
                errors.append(f"{model}: not found")
                continue
            elif e.code in (400, 401, 403):
                return None, f"API key error (HTTP {e.code}): {err_msg}"
            else:
                errors.append(f"{model}: HTTP {e.code}")
                continue
        except Exception as ex:
            errors.append(f"{model}: {str(ex)}")
            continue
    return None, "All models failed. Wait 1 minute and try again. (" + " | ".join(errors) + ")"

def safe_parse_json(text):
    text = text.strip()
    # Strip ALL variations of code fences
    for fence in ["```json", "```JSON", "```"]:
        if text.startswith(fence):
            text = text[len(fence):]
            break
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    # Extract outermost { } block
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e > s:
        text = text[s:e+1]
    return json.loads(text)

def ai_match_gemini(job_title, job_desc, job_location, job_category, applicants, mode="vendor"):
    if not applicants:
        return None, "No applicants found."

    import os
    GEMINI_API_KEY = ""
    try:
        with open("gemini_key.txt", "r") as kf:
            k = kf.read().strip()
            if k and len(k) > 10:
                GEMINI_API_KEY = k
    except:
        pass
    if not GEMINI_API_KEY:
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
    if not GEMINI_API_KEY:
        return None, "API key not found. Run Cell 2 in the notebook to set your Gemini API key."

    if mode == "vendor":
        # Build simple numbered list
        lines = []
        for i, a in enumerate(applicants):
            aid, name, loc, msg, date_applied, status, phone = a
            lines.append(f"{i+1}. {name} from {loc or 'unknown location'}")
        applicant_list = "\n".join(lines)

        prompt = (
            f"Job location: {job_location}. Category: {job_category}.\n"
            f"Rank these applicants from nearest to farthest from {job_location}:\n"
            f"{applicant_list}\n\n"
            f"Return a JSON object with this exact structure:\n"
            f'{{"ranked_applicants":[{{"rank":1,"name":"exact name from list","location":"their location","score":9,"proximity":"Near","recommendation":"Highly Recommended","summary":"why"}}],"hiring_tip":"one tip"}}\n'
            f"proximity must be Near, Medium, or Far only. Keep summary under 8 words."
        )
    else:
        lines = []
        for i, a in enumerate(applicants):
            ji, jtitle, jvendor, jloc, jsal, jcat, jdesc, jdate, jdeadline, jmonths, jstatus, jcount = a
            lines.append(f"{i+1}. {jtitle} in {jloc}")
        job_list = "\n".join(lines)
        worker_loc = job_location

        prompt = (
            f"Worker location: {worker_loc}.\n"
            f"Rank these jobs from nearest to farthest from {worker_loc}:\n"
            f"{job_list}\n\n"
            f"Return a JSON object with this exact structure:\n"
            f'{{"ranked_jobs":[{{"rank":1,"title":"exact title","location":"job location","proximity":"Near","score":9,"recommendation":"Best Match","summary":"why"}}],"search_tip":"one tip"}}\n'
            f"proximity must be Near, Medium, or Far only. Keep summary under 8 words."
        )

    text, err = call_gemini_api(prompt, GEMINI_API_KEY)
    if err:
        return None, f"AI error: {err}"
    try:
        result = safe_parse_json(text)
        return result, None
    except Exception as ex:
        # Last resort: show raw so user can see what came back
        return None, f"Could not parse response ({str(ex)}). Raw text: {text[:300]}"

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## VendorsLink")
    st.markdown("---")
    if st.session_state.logged_in:
        role_label = "[Vendor]" if st.session_state.user_role == "Vendor" else "[Worker]"
        st.success(f"{role_label} {st.session_state.user_name}")
        st.caption(f"Role: {st.session_state.user_role}")
        if st.session_state.user_location:
            st.caption(f"Location: {st.session_state.user_location}")
        st.markdown("---")
        if st.session_state.user_role == "Vendor":
            page = st.radio("Menu", ["Post a Job","My Jobs","Applications","Hire Worker","AI Smart Match"])
        else:
            page = st.radio("Menu", ["Browse Jobs","My Applications","AI Job Match"])
        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    else:
        _options = ["Home","Register","Login"]
        _nav     = st.session_state.get("nav_page","Home")
        _default = _options.index(_nav) if _nav in _options else 0
        page = st.radio("Menu", _options, index=_default)
        # Clear after reading so it doesn't stay stuck on Login forever
        st.session_state.nav_page = "Home"
    st.markdown("---")
    st.caption("VendorsLink")

# ============================================================
# REGISTRATION POPUP
# ============================================================
if st.session_state.get("show_reg_popup"):
    st.balloons()
    role = st.session_state.get("popup_msg","")
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);color:white;border-radius:20px;
         padding:2rem;text-align:center;margin-bottom:1.5rem;
         box-shadow:0 8px 32px rgba(26,115,232,0.4)">
      <div style="font-size:3rem">&#127881;</div>
      <h2 style="color:white;margin:0.5rem 0">Welcome to VendorsLink!</h2>
      <p style="opacity:0.9;font-size:1rem">You have successfully registered as a <b>{role}</b>.</p>
      <p style="opacity:0.8;font-size:0.9rem">Click below to go to Login.</p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Continue to Login", type="primary", use_container_width=True, key="reg_popup_btn"):
        st.session_state.show_reg_popup = False
        st.session_state.popup_msg      = ""
        st.session_state.nav_page       = "Login"
        st.rerun()
    st.stop()

# ============================================================
# HIRE CELEBRATION POPUP
# ============================================================
if st.session_state.get("show_hire_popup"):
    st.balloons()
    wname = st.session_state.get("hired_worker_name","Worker")
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#28a745,#155724);color:white;border-radius:20px;
         padding:2.5rem;text-align:center;margin-bottom:1.5rem;
         box-shadow:0 8px 32px rgba(40,167,69,0.4)">
      <div style="font-size:3.5rem">&#127942;</div>
      <h2 style="color:white;margin:0.5rem 0">Hiring Confirmed!</h2>
      <p style="opacity:0.9;font-size:1.1rem"><b>{wname}</b> has been successfully hired!</p>
      <p style="opacity:0.8;font-size:0.9rem">The job listing has been closed and all other applicants have been notified.</p>
      <div style="font-size:2rem;margin-top:1rem">&#11088; &#127881; &#11088;</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Great!", type="primary", use_container_width=True):
        st.session_state.show_hire_popup = False
        st.rerun()
    st.stop()

# ============================================================
# APPLY SUCCESS POPUP
# ============================================================
if st.session_state.get("show_apply_popup"):
    st.balloons()
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a73e8,#6a1be8);color:white;border-radius:20px;
         padding:2.5rem;text-align:center;margin-bottom:1.5rem;
         box-shadow:0 8px 32px rgba(106,27,232,0.4)">
      <div style="font-size:3.5rem">&#128640;</div>
      <h2 style="color:white;margin:0.5rem 0">Application Submitted!</h2>
      <p style="opacity:0.9;font-size:1rem">Your application has been sent to the vendor.</p>
      <p style="opacity:0.8;font-size:0.9rem">Track your application status in My Applications.</p>
      <div style="font-size:2rem;margin-top:1rem">&#127919; &#128640; &#127919;</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("View My Applications", type="primary", use_container_width=True):
        st.session_state.show_apply_popup = False
        st.session_state.selected_job = None
        st.rerun()
    st.stop()

# ============================================================
# JOB POSTED POPUP
# ============================================================
if st.session_state.get("show_job_popup"):
    st.balloons()
    jmsg = st.session_state.get("job_popup_msg","")
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);color:white;border-radius:20px;
         padding:2.5rem;text-align:center;margin-bottom:1.5rem;
         box-shadow:0 8px 32px rgba(26,115,232,0.4)">
      <div style="font-size:3.5rem">&#128196;</div>
      <h2 style="color:white;margin:0.5rem 0">Job Posted Successfully!</h2>
      <p style="opacity:0.9;font-size:1rem"><b>{jmsg}</b></p>
      <p style="opacity:0.8;font-size:0.9rem">Workers can now find and apply for your job.</p>
      <div style="font-size:2rem;margin-top:1rem">&#127881; &#128196; &#127881;</div>
    </div>
    """, unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Post Another Job", use_container_width=True):
            st.session_state.show_job_popup  = False
            st.session_state.job_popup_msg   = ""
            st.rerun()
    with c2:
        if st.button("View My Jobs", type="primary", use_container_width=True):
            st.session_state.show_job_popup  = False
            st.session_state.job_popup_msg   = ""
            st.rerun()
    st.stop()

# ============================================================
# HOME
# ============================================================
if not st.session_state.logged_in and page == "Home":
    st.markdown('<div class="main-title">VendorsLink</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Connecting Vendors and Workers Seamlessly</div>', unsafe_allow_html=True)
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""<div class="card card-vendor">
        <h3>For Vendors</h3>
        <ul><li>Post jobs with deadlines</li>
        <li>Manage all applications</li>
        <li>One-click hiring with auto-close</li>
        <li>AI Smart Match - rank nearest workers</li></ul>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("""<div class="card card-worker">
        <h3>For Workers</h3>
        <ul><li>Browse jobs near your location</li>
        <li>View full details and apply</li>
        <li>Track all your applications</li>
        <li>AI Job Match - find nearest jobs</li></ul>
        </div>""", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("""<div class="ai-hero">
    <h3 style="color:white;margin:0">Smart AI Matching - Find the Right Person, Right Location</h3>
    <p style="color:rgba(255,255,255,0.85);margin:0.4rem 0 0 0">AI ranks workers and jobs by proximity so vendors hire nearby workers and workers find nearby jobs.</p>
    </div>""", unsafe_allow_html=True)
    st.info("Use the sidebar to Register or Login to get started!")

# ============================================================
# REGISTER
# ============================================================
elif not st.session_state.logged_in and page == "Register":
    st.markdown("## Register")
    st.markdown("---")
    with st.form("rf"):
        c1, c2 = st.columns(2)
        with c1:
            rn       = st.text_input("Full Name *")
            re_input = st.text_input("Email *")
            rph      = st.text_input("Phone Number")
        with c2:
            rr    = st.selectbox("Register As *", ["Vendor","Worker"])
            rloc  = st.text_input("Your City / Location *")
            rp    = st.text_input("Password *", type="password")
            rc    = st.text_input("Confirm Password *", type="password")
        if st.form_submit_button("Register", use_container_width=True, type="primary"):
            ok, msg = register(rn, re_input, rp, rc, rr, rph, rloc)
            if ok:
                st.session_state.show_reg_popup = True
                st.session_state.popup_msg = rr
                st.rerun()
            else:
                st.error(f"Error: {msg}")

# ============================================================
# LOGIN
# ============================================================
elif not st.session_state.logged_in and page == "Login":
    st.markdown("## Login")
    st.markdown("---")
    with st.form("lf"):
        c1, c2 = st.columns(2)
        with c1:
            le = st.text_input("Email *")
            lp = st.text_input("Password *", type="password")
        with c2:
            lr = st.selectbox("Login As *", ["Vendor","Worker"])
        if st.form_submit_button("Login", use_container_width=True, type="primary"):
            u = login(le, lp, lr)
            if u:
                st.session_state.logged_in     = True
                st.session_state.user_id       = u[0]
                st.session_state.user_name     = u[1]
                st.session_state.user_role     = u[2]
                st.session_state.user_email    = u[3]
                st.session_state.user_location = u[4] or ""
                st.success(f"Welcome back, {u[1]}!")
                st.rerun()
            else:
                st.error("Invalid credentials or wrong role selected.")

# ============================================================
# VENDOR: POST JOB
# ============================================================
elif st.session_state.logged_in and page == "Post a Job":
    st.markdown("## Post a New Job")
    st.markdown("---")
    with st.form("pf"):
        c1, c2 = st.columns(2)
        with c1:
            jt  = st.text_input("Job Title *")
            jl  = st.text_input("Location *", value=st.session_state.user_location)
            js  = st.text_input("Salary / Pay Rate")
            jmo = st.number_input("Job Duration (months) *", min_value=1, max_value=24, value=1, step=1)
        with c2:
            jc  = st.selectbox("Category", CATS)
            jd  = st.text_area("Job Description *", height=150,
                               placeholder="Describe the job requirements, experience needed...")
        if st.form_submit_button("Post Job", use_container_width=True, type="primary"):
            if not all([jt.strip(), jd.strip(), jl.strip()]):
                st.error("Title, Description and Location are required.")
            elif vendor_already_posted(st.session_state.user_id, jt):
                st.error(f"You already posted a job titled '{jt}'. Same vendor cannot post the same job twice.")
            else:
                post_job(st.session_state.user_id, jt, jd, jl, js, jc, int(jmo))
                st.session_state.show_job_popup = True
                st.session_state.job_popup_msg  = f"{jt} | {jmo} month(s) | {jl}"
                st.rerun()

# ============================================================
# VENDOR: MY JOBS
# ============================================================
elif st.session_state.logged_in and page == "My Jobs":
    st.markdown("## My Posted Jobs")
    st.markdown("---")
    jobs = vendor_jobs(st.session_state.user_id)
    if not jobs:
        st.info("No jobs posted yet.")
    else:
        open_j   = [j for j in jobs if j[8] == 0]
        closed_j = [j for j in jobs if j[8] == 1]
        c1,c2,c3 = st.columns(3)
        c1.metric("Total", len(jobs))
        c2.metric("Open", len(open_j))
        c3.metric("Closed", len(closed_j))
        if open_j:
            st.markdown("### Open Jobs")
            for j in open_j:
                jid,jtitle,jloc,jsal,jcat,jdate,jdeadline,jmo,jclosed,jstatus,jcount = j
                dl = days_left(jdeadline) if jdeadline else None
                status_badge = "Currently Accepting Applications" if jstatus=="accepting" else "Reviewing Applications"
                badge_col = "#1e7e34" if jstatus=="accepting" else "#e65100"
                with st.expander(f"Job #{jid} | {jtitle} | {jloc} | {jcount} applicant(s)"):
                    c1,c2,c3 = st.columns(3)
                    c1.markdown(f"**Category:** {jcat}")
                    c2.markdown(f"**Salary:** {jsal or 'N/A'}")
                    c3.markdown(f"**Duration:** {jmo} month(s)")
                    st.markdown(f'<span style="background:{badge_col};color:white;padding:3px 14px;border-radius:20px;font-size:0.85rem;font-weight:600">{status_badge}</span>', unsafe_allow_html=True)
                    if dl is not None and dl <= 5:
                        st.warning(f"Deadline approaching: {dl} day(s) left")
                    c1,c2 = st.columns(2)
                    with c1:
                        if jstatus == "accepting":
                            if st.button(f"Switch to Reviewing", key=f"rev_{jid}"):
                                set_job_status(jid, st.session_state.user_id, "reviewing")
                                st.success("Status changed to Reviewing. No new applications will be accepted.")
                                st.rerun()
                        else:
                            if st.button(f"Switch to Accepting", key=f"acc_{jid}"):
                                set_job_status(jid, st.session_state.user_id, "accepting")
                                st.success("Status changed to Accepting Applications.")
                                st.rerun()
                    with c2:
                        if st.button(f"Close Job", key=f"close_{jid}"):
                            close_job_manually(jid, st.session_state.user_id)
                            st.success("Job closed.")
                            st.rerun()
        if closed_j:
            st.markdown("### Closed / Hired Jobs")
            for j in closed_j:
                jid,jtitle,jloc,jsal,jcat,jdate,jdeadline,jmo,jclosed,jstatus,jcount = j
                label = "HIRED" if jstatus=="hired" else "CLOSED"
                with st.expander(f"Job #{jid} | {jtitle} | {jloc} | {label} | {jcount} applicant(s)"):
                    c1,c2 = st.columns(2)
                    c1.markdown(f"**Category:** {jcat} | **Duration:** {jmo} month(s)")
                    c2.markdown(f"**Posted:** {jdate}")

# ============================================================
# VENDOR: APPLICATIONS
# ============================================================
elif st.session_state.logged_in and page == "Applications":
    st.markdown("## Applications on Your Jobs")
    st.markdown("---")
    apps = vendor_apps(st.session_state.user_id)
    if not apps:
        st.info("No applications received yet.")
    else:
        pending = [a for a in apps if a[6]=="Pending"]
        st.success(f"Total: {len(apps)} | Pending: {len(pending)}")
        for a in apps:
            aid,jt,wn,we,wp,wm,ws,wd,jid,jstatus = a
            ws_color = {"Pending":"#f0a500","Accepted":"#1e7e34","Rejected":"#c0392b"}.get(ws,"#555")
            with st.expander(f"App #{aid} | {jt} | Worker: {wn} | Status: {ws}"):
                c1,c2,c3 = st.columns(3)
                c1.markdown(f"**Name:** {wn}")
                c2.markdown(f"**Email:** {we}")
                c3.markdown(f"**Phone:** {wp or 'N/A'}")
                st.markdown(f"**Message:** {wm or 'No message'}")
                st.caption(f"Applied on: {wd} | Job Status: {jstatus}")

# ============================================================
# VENDOR: HIRE WORKER
# ============================================================
elif st.session_state.logged_in and page == "Hire Worker":
    st.markdown("## Hire a Worker")
    st.markdown("---")
    st.info("Select an application and confirm hiring. This will accept that worker, reject all others, and close the job.")
    apps = vendor_apps(st.session_state.user_id)
    pending_apps = [a for a in apps if a[6] == "Pending"]
    if not pending_apps:
        st.info("No pending applications to hire from.")
    else:
        with st.form("hire_form"):
            ch = {a[0]: f"#{a[0]} | Job: {a[1]} | Worker: {a[2]} | Phone: {a[4] or 'N/A'}" for a in pending_apps}
            sel = st.selectbox("Select Application to Hire", list(ch.keys()), format_func=lambda x: ch[x])
            selected_app = next((a for a in pending_apps if a[0]==sel), None)
            if selected_app:
                st.markdown(f"""
                **Worker:** {selected_app[2]}
                **Email:** {selected_app[3]}
                **Phone:** {selected_app[4] or 'N/A'}
                **Job:** {selected_app[1]}
                **Message:** {selected_app[5] or 'No message'}
                """)
            st.warning("Confirming hire will close the job and reject all other applicants for this job.")
            confirmed = st.checkbox("I confirm that I want to hire this worker")
            if st.form_submit_button("Confirm Hire", use_container_width=True, type="primary"):
                if not confirmed:
                    st.error("Please check the confirmation box first.")
                else:
                    jid = selected_app[8]
                    wname = hire_worker(sel, jid, st.session_state.user_id)
                    st.session_state.show_hire_popup = True
                    st.session_state.hired_worker_name = wname
                    st.rerun()

# ============================================================
# VENDOR: AI SMART MATCH
# ============================================================
elif st.session_state.logged_in and page == "AI Smart Match":
    st.markdown("""<div class="ai-hero">
    <h2 style="color:white;margin:0">AI Smart Match</h2>
    <p style="color:rgba(255,255,255,0.85);margin:0.4rem 0 0 0;font-size:0.95rem">Finds the nearest workers to your job location and ranks them by proximity and fit.</p>
    </div>""", unsafe_allow_html=True)

    open_jobs = get_vendor_open_jobs(st.session_state.user_id)

    # API Key section - always show at top of AI pages
    import os
    open_jobs = get_vendor_open_jobs(st.session_state.user_id)

    if not open_jobs:
        st.info("No open jobs. Post a job first.")
    else:
        job_options = {j[0]: f"#{j[0]} - {j[1]} ({j[4]}) - {j[3]}" for j in open_jobs}
        selected_jid = st.selectbox("Select Job to Analyze", list(job_options.keys()), format_func=lambda x: job_options[x])
        sel_job = next((j for j in open_jobs if j[0]==selected_jid), None)
        applicants = get_apps_for_job(selected_jid)

        if not applicants:
            st.warning("No applicants yet for this job.")
        else:
            st.info(f"Found {len(applicants)} applicant(s). AI will rank them by proximity to **{sel_job[3]}**.")
            with st.expander("View All Applicants"):
                for a in applicants:
                    aid,name,loc,msg,date_applied,status,phone = a
                    st.markdown(f"**{name}** | Location: {loc or 'N/A'} | Phone: {phone or 'N/A'} | Status: {status}")
                    st.caption(f"Message: {msg or 'No message'} | Applied: {date_applied}")
                    st.markdown("---")

            if st.button("Run AI Smart Match - Find Nearest Workers", type="primary", use_container_width=True):
                with st.spinner("AI is analyzing proximity... please wait..."):
                    jid,jtitle,jdesc,jloc,jcat = sel_job
                    result, err = ai_match_gemini(jtitle, jdesc, jloc, jcat, applicants, mode="vendor")
                    if err:
                        st.error(f"Error: {err}")
                    else:
                        st.session_state.ai_result = result
                        st.rerun()

            if st.session_state.ai_result:
                result = st.session_state.ai_result
                st.markdown("---")
                st.markdown("### AI Ranking - Nearest Workers First")
                ranked = result.get("ranked_applicants", [])
                tip    = result.get("hiring_tip","")
                for r in ranked:
                    rank  = r.get("rank","?")
                    name  = r.get("name","?")
                    loc   = r.get("location","?")
                    score = r.get("score",0)
                    prox  = r.get("proximity","?")
                    rec   = r.get("recommendation","")
                    summ  = r.get("summary","")
                    prox_color = {"Near":"#1e7e34","Medium":"#e65100","Far":"#c0392b"}.get(prox,"#555")
                    rec_color  = {"Highly Recommended":"#1e7e34","Recommended":"#1a73e8","Not Recommended":"#c0392b"}.get(rec,"#555")
                    medal = {1:"BEST MATCH",2:"2nd Best",3:"3rd Best"}.get(rank,f"#{rank}")
                    st.markdown(f"""
                    <div class="ai-card">
                      <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
                        <div class="ai-rank">{medal}</div>
                        <div style="flex:1">
                          <div class="ai-name">{name}</div>
                          <div style="font-size:0.88rem;color:#555">Location: {loc}</div>
                          <div class="ai-score">Match Score: {score}/10</div>
                        </div>
                        <div style="text-align:right">
                          <span style="background:{prox_color};color:white;padding:3px 12px;border-radius:20px;font-size:0.8rem;font-weight:700;display:block;margin-bottom:4px">{prox} from Job</span>
                          <span style="background:{rec_color};color:white;padding:3px 12px;border-radius:20px;font-size:0.8rem;font-weight:700">{rec}</span>
                        </div>
                      </div>
                      <div class="ai-reason" style="margin-top:0.6rem"><em>{summ}</em></div>
                    </div>
                    """, unsafe_allow_html=True)
                if tip:
                    st.markdown("---")
                    st.info(f"AI Hiring Tip: {tip}")
                if st.button("Clear & Re-run", use_container_width=True):
                    st.session_state.ai_result = None
                    st.rerun()

# ============================================================
# WORKER: BROWSE JOBS
# ============================================================
elif st.session_state.logged_in and page == "Browse Jobs":
    if st.session_state.selected_job:
        job = get_job_by_id(st.session_state.selected_job)
        if job:
            ji,jtitle,jvendor,jloc,jsal,jcat,jdesc,jdate,jdeadline,jmo,jclosed,jstatus = job
            dl = days_left(jdeadline) if jdeadline else None
            if st.button("Back to Jobs List"):
                st.session_state.selected_job = None
                st.rerun()
            st.markdown("---")
            st.markdown(f"## {jtitle}")
            c1,c2,c3,c4 = st.columns(4)
            c1.markdown(f"**Vendor:** {jvendor}")
            c2.markdown(f"**Location:** {jloc}")
            c3.markdown(f"**Salary:** {jsal or 'N/A'}")
            c4.markdown(f"**Duration:** {jmo} month(s)")
            st.markdown("---")
            if jstatus == "accepting":
                st.success("Currently Accepting Applications")
            elif jstatus == "reviewing":
                st.warning("Currently Reviewing Applications - Not accepting new applications")
            if jdeadline and dl is not None:
                if dl <= 2:
                    st.warning(f"Closing soon! Only {dl} day(s) left.")
                elif dl >= 0:
                    st.info(f"Apply before: {jdeadline} ({dl} days left)")
            st.markdown("### Job Description")
            st.markdown(jdesc)
            st.markdown("---")
            already_applied = worker_already_applied(ji, st.session_state.user_id)
            active_offers   = count_active_offers(st.session_state.user_id)
            if jclosed==1 or (dl is not None and dl<0):
                st.error("This job is closed.")
            elif jstatus == "reviewing":
                st.warning("This job is reviewing existing applications. New applications are not being accepted.")
            elif already_applied:
                st.info("You have already applied to this job.")
            elif active_offers >= 3:
                st.warning("You have 3 active job offers pending. Please respond to them before applying to more jobs.")
            else:
                st.markdown("### Apply Now")
                with st.form("apply_form"):
                    amsg = st.text_area("Cover Message (optional)", height=120,
                                        placeholder="Briefly describe why you are a good fit...")
                    st.info(f"Your phone number ({st.session_state.get('user_phone','on profile')}) will be shared with the vendor.")
                    if st.form_submit_button("Submit Application", use_container_width=True, type="primary"):
                        ok, msg = apply_job(ji, st.session_state.user_id, amsg)
                        if ok:
                            st.session_state.show_apply_popup = True
                            st.rerun()
                        else:
                            st.error(msg)
        else:
            st.error("Job not found.")
            st.session_state.selected_job = None
            st.rerun()
    else:
        st.markdown("## Browse Jobs")
        st.markdown("---")
        with st.form("sf"):
            c1,c2,c3 = st.columns(3)
            sk = c1.text_input("Keyword")
            sl = c2.text_input("Location", value=st.session_state.user_location)
            sc = c3.selectbox("Category", ["All"]+CATS)
            st.form_submit_button("Search Jobs", use_container_width=True, type="primary")
        jobs = search_jobs(sk, sl, sc)
        if not jobs:
            st.info("No open jobs found. Try different filters.")
        else:
            st.success(f"Found {len(jobs)} open job(s)")
            st.markdown("---")
            for j in jobs:
                ji,jtitle,jvendor,jloc,jsal,jcat,jdesc,jdate,jdeadline,jmo,jstatus,jcount = j
                dl = days_left(jdeadline) if jdeadline else None
                dl_text = f"{dl} days left" if dl is not None and dl>0 else "Closing today"
                badge_color = "#e65100" if dl is not None and dl<=2 else "#1e7e34"
                status_text = "Currently Accepting Applications" if jstatus=="accepting" else "Reviewing Applications"
                status_color = "#1e7e34" if jstatus=="accepting" else "#e65100"
                st.markdown(f"""
                <div class="job-card">
                  <div class="job-title">{jtitle}</div>
                  <div class="job-meta">{jvendor} | {jloc} | {jsal or 'Salary N/A'} | {jmo} month(s)</div>
                  <span class="badge badge-cat">{jcat}</span>
                  <span style="background:{status_color};color:white;padding:2px 10px;border-radius:20px;font-size:0.78rem;font-weight:600">{status_text}</span>
                  <span style="font-size:0.82rem;color:{badge_color};font-weight:600;margin-left:8px">Deadline: {jdeadline} ({dl_text})</span>
                  <span style="font-size:0.82rem;color:#888;margin-left:8px">{jcount} applicant(s)</span>
                  <br><br>
                  <div style="color:#444;font-size:0.92rem">{jdesc[:150]}{'...' if len(jdesc)>150 else ''}</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"View Details & Apply  [Job #{ji}]", key=f"view_{ji}", use_container_width=True):
                    st.session_state.selected_job = ji
                    st.rerun()
                st.markdown("")

# ============================================================
# WORKER: MY APPLICATIONS
# ============================================================
elif st.session_state.logged_in and page == "My Applications":
    st.markdown("## My Applications")
    st.markdown("---")
    apps = worker_apps(st.session_state.user_id)
    active_offers = count_active_offers(st.session_state.user_id)
    if active_offers >= 3:
        st.warning(f"You have {active_offers} active job offers. You cannot apply to more jobs until you respond to them.")
    if not apps:
        st.info("No applications yet. Go to Browse Jobs.")
    else:
        ss = [a[5] for a in apps]
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total",    len(apps))
        c2.metric("Pending",  ss.count("Pending"))
        c3.metric("Accepted", ss.count("Accepted"))
        c4.metric("Rejected", ss.count("Rejected"))
        st.markdown("---")
        for a in apps:
            aid,at,av,alo,asa,ast,adate,jclosed,jstatus = a
            closed_note = " [Job Closed]" if jclosed==1 else ""
            with st.expander(f"App #{aid} | {at} | {av} | Status: {ast}{closed_note}"):
                c1,c2,c3 = st.columns(3)
                c1.markdown(f"**Location:** {alo}")
                c2.markdown(f"**Salary:** {asa or 'N/A'}")
                c3.markdown(f"**Applied:** {adate}")
                if ast == "Accepted":
                    st.success("Congratulations! You have been hired!")
                    st.markdown("""
                    <div style="background:linear-gradient(135deg,#28a745,#155724);color:white;border-radius:12px;padding:1rem;text-align:center">
                      <div style="font-size:2rem">&#127942;</div>
                      <b>You got the job! The vendor will contact you soon.</b>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"Reject this Offer", key=f"rej_{aid}"):
                        reject_offer(aid, st.session_state.user_id)
                        st.success("Offer rejected. You can now apply to other jobs.")
                        st.rerun()
                elif ast == "Rejected":
                    st.warning("Not selected this time. Keep applying!")
                elif jstatus == "reviewing":
                    st.info("Vendor is reviewing applications. Hang tight!")
                elif jclosed == 1:
                    st.info("This job has been filled.")

# ============================================================
# WORKER: AI JOB MATCH
# ============================================================
elif st.session_state.logged_in and page == "AI Job Match":
    st.markdown("""<div class="ai-hero">
    <h2 style="color:white;margin:0">AI Job Match</h2>
    <p style="color:rgba(255,255,255,0.85);margin:0.4rem 0 0 0;font-size:0.95rem">Finds the nearest open jobs to your location and ranks them by proximity.</p>
    </div>""", unsafe_allow_html=True)

    worker_loc = st.session_state.user_location

    if not worker_loc:
        st.warning("Your location is not set. Please re-register with your city.")
    else:
        st.info(f"Your Location: {worker_loc}")
        with st.form("wai_form"):
            cat_filter = st.selectbox("Filter by Category (optional)", ["All"]+CATS)
            run_btn = st.form_submit_button("Find Nearest Jobs Using AI", use_container_width=True, type="primary")

        if run_btn:
            all_jobs = search_jobs("", "", cat_filter)
            if not all_jobs:
                st.info("No open jobs available right now.")
            else:
                with st.spinner("AI is finding the nearest jobs to you..."):
                    result, err = ai_match_gemini("", "", worker_loc, "", all_jobs, mode="worker")
                    if err:
                        st.error(f"Error: {err}")
                    else:
                        st.session_state.ai_result = result
                        st.rerun()

        if st.session_state.ai_result and "ranked_jobs" in st.session_state.ai_result:
            result = st.session_state.ai_result
            st.markdown("---")
            st.markdown("### Nearest Jobs to You")
            ranked = result.get("ranked_jobs",[])
            tip    = result.get("search_tip","")
            for r in ranked:
                rank  = r.get("rank","?")
                title = r.get("title","?")
                loc   = r.get("location","?")
                prox  = r.get("proximity","?")
                score = r.get("score",0)
                rec   = r.get("recommendation","")
                summ  = r.get("summary","")
                prox_color = {"Near":"#1e7e34","Medium":"#e65100","Far":"#c0392b"}.get(prox,"#555")
                medal = {1:"NEAREST",2:"2nd Nearest",3:"3rd Nearest"}.get(rank,f"#{rank}")
                st.markdown(f"""
                <div class="ai-card">
                  <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
                    <div class="ai-rank">{medal}</div>
                    <div style="flex:1">
                      <div class="ai-name">{title}</div>
                      <div style="font-size:0.88rem;color:#555">Location: {loc}</div>
                      <div class="ai-score">Match Score: {score}/10</div>
                    </div>
                    <span style="background:{prox_color};color:white;padding:3px 14px;border-radius:20px;font-size:0.82rem;font-weight:700">{prox} from You</span>
                  </div>
                  <div class="ai-reason" style="margin-top:0.6rem"><em>{summ}</em></div>
                </div>
                """, unsafe_allow_html=True)
            if tip:
                st.markdown("---")
                st.info(f"AI Tip: {tip}")
            if st.button("Clear & Search Again", use_container_width=True):
                st.session_state.ai_result = None
                st.rerun()

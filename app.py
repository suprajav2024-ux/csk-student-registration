from flask import Flask, render_template, request, redirect, url_for, session
import csv
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os, json, time

# ---------------- APP ----------------
app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- CACHE ----------------
CACHE = {}
CACHE_TTL = 60

def clear_cache(user):
    CACHE.pop(user, None)

# ---------------- FILES ----------------
FELLOWS_CSV = "Fellow Details _ School + Login - Sheet1.csv"
EVENTS_CSV = "Event List - Sheet2.csv"
SHEET_NAME = "CSK Student Event Registrations"

# ---------------- TIME SLOT NORMALIZATION ----------------
TIME_SLOT_MAP = {
    "10:00-11:00": "10-11am",
    "11:00-12:00": "11-12pm",
    "1:00-2:00": "1-2pm",
    "13:00-14:00": "1-2pm",
    "2:00-3:00": "2-3pm",
    "14:00-15:00": "2-3pm"
}

# ---------------- GOOGLE SHEET ----------------
def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDS"]),
        scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1


def write_to_google_sheet(data):
    sheet = get_sheet()
    sheet.append_row([
        datetime.now().strftime("%d-%m-%Y %H:%M"),
        data["school"],
        data["grade"],
        data["section"],
        data["name"],
        data["event_10_11"],
        data["event_11_12"],
        data["event_1_2"],
        data["event_2_3"],
        data["created_by_email"],
        data["action"]
    ])


def read_latest_students(user_email):
    sheet = get_sheet()
    rows = sheet.get_all_records()

    latest = {}
    for r in rows:
        if r["Created By Email"] != user_email:
            continue

        ts = datetime.strptime(r["Timestamp"], "%d-%m-%Y %H:%M")
        name = r["Student Name"]

        if name not in latest or ts > latest[name]["_ts"]:
            r["_ts"] = ts
            latest[name] = r

    return [r for r in latest.values() if r["Action"] != "DELETED"]


def get_students_cached(user):
    now = time.time()
    if user in CACHE:
        data, ts = CACHE[user]
        if now - ts < CACHE_TTL:
            return data

    data = read_latest_students(user)
    CACHE[user] = (data, now)
    return data

# ---------------- LOADERS ----------------
def load_fellows():
    fellows = {}
    with open(FELLOWS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fellows[row["Email"]] = {
                "password": row["Password"],
                "school": row["School"]
            }
    return fellows


def load_events():
    event_options = {}
    event_slot_map = {}

    with open(EVENTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            grade = row["Class"]
            event = row["Event"]

            raw_s1 = row.get("Time Slot 1", "").strip()
            raw_s2 = row.get("Time Slot 2", "").strip()

            s1 = TIME_SLOT_MAP.get(raw_s1, raw_s1)
            s2 = TIME_SLOT_MAP.get(raw_s2, raw_s2)

            event_options.setdefault(grade, {
                "10-11am": [],
                "11-12pm": [],
                "1-2pm": [],
                "2-3pm": []
            })

            if s1 and s1 in event_options[grade]:
                event_options[grade][s1].append(event)

            if s2 and s2 in event_options[grade]:
                event_options[grade][s2].append(event)

            # 🔑 BUILD EVENT → SLOT MAP
            slots = []
            if s1:
                slots.append(s1)
            if s2:
                slots.append(s2)

            if len(slots) > 1:
                event_slot_map[event] = slots

    for g in event_options:
        for s in event_options[g]:
            if "Not participating" not in event_options[g][s]:
                event_options[g][s].insert(0, "Not participating")

    return event_options, event_slot_map


EVENT_OPTIONS, EVENT_SLOT_MAP = load_events()

# ---------------- AUTH ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    fellows = load_fellows()
    if request.method == "POST":
        email = request.form["email"]
        pwd = request.form["password"]

        if email in fellows and fellows[email]["password"] == pwd:
            session["user_id"] = email
            session["school"] = fellows[email]["school"]
            return redirect(url_for("students"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- STUDENTS ----------------
@app.route("/students")
def students():
    if "user_id" not in session:
        return redirect(url_for("login"))

    students = get_students_cached(session["user_id"])
    return render_template("students.html", students=students)

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        write_to_google_sheet({
            "name": request.form["name"],
            "grade": request.form["grade"],
            "section": request.form["section"],
            "school": session["school"],
            "event_10_11": request.form["event_10_11"],
            "event_11_12": request.form["event_11_12"],
            "event_1_2": request.form["event_1_2"],
            "event_2_3": request.form["event_2_3"],
            "created_by_email": session["user_id"],
            "action": "CREATED"
        })

        clear_cache(session["user_id"])
        return redirect(url_for("students"))

    return render_template(
        "register.html",
        event_options=EVENT_OPTIONS,
        event_slot_map=EVENT_SLOT_MAP
    )

# ---------------- EDIT ----------------
@app.route("/edit/<name>", methods=["GET", "POST"])
def edit_student(name):
    if "user_id" not in session:
        return redirect(url_for("login"))

    students = get_students_cached(session["user_id"])
    student = next((s for s in students if s["Student Name"] == name), None)

    if not student:
        return redirect(url_for("students"))

    if request.method == "POST":
        write_to_google_sheet({
            "name": request.form["name"],
            "grade": request.form["grade"],
            "section": request.form["section"],
            "school": session["school"],
            "event_10_11": request.form["event_10_11"],
            "event_11_12": request.form["event_11_12"],
            "event_1_2": request.form["event_1_2"],
            "event_2_3": request.form["event_2_3"],
            "created_by_email": session["user_id"],
            "action": "UPDATED"
        })

        clear_cache(session["user_id"])
        return redirect(url_for("students"))

    return render_template(
        "edit_student.html",
        student=student,
        event_options=EVENT_OPTIONS,
        event_slot_map=EVENT_SLOT_MAP
    )

# ---------------- DELETE ----------------
@app.route("/delete/<name>", methods=["POST"])
def delete_student(name):
    if "user_id" not in session:
        return redirect(url_for("login"))

    write_to_google_sheet({
        "name": name,
        "grade": "",
        "section": "",
        "school": session["school"],
        "event_10_11": "",
        "event_11_12": "",
        "event_1_2": "",
        "event_2_3": "",
        "created_by_email": session["user_id"],
        "action": "DELETED"
    })

    clear_cache(session["user_id"])
    return redirect(url_for("students"))

# ---------------- EVENT VIEW ----------------
@app.route("/events")
def events():
    if "user_id" not in session:
        return redirect(url_for("login"))

    students = get_students_cached(session["user_id"])
    events = {}

    for s in students:
        student_info = {
            "name": s["Student Name"],
            "grade": s["Class"],
            "section": s["Section"]
        }

        slot_map = {
            "10-11am": s["Event 10-11"],
            "11-12pm": s["Event 11-12"],
            "1-2pm": s["Event 1-2"],
            "2-3pm": s["Event 2-3"]
        }

        for slot, event in slot_map.items():
            if not event or event == "Not participating":
                continue

            events.setdefault(event, {"students": [], "slots": set()})

            if student_info not in events[event]["students"]:
                events[event]["students"].append(student_info)

            events[event]["slots"].add(slot)

    for event in events:
        slots = sorted(events[event]["slots"])
        if slots:
            start = slots[0].split("-")[0]
            end = slots[-1].split("-")[1]
            events[event]["time"] = f"{start}-{end}"
        else:
            events[event]["time"] = ""

    return render_template("event_view.html", events=events)

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

from flask import Flask, render_template, request, redirect, url_for, session
import csv
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json
import time
CACHE = {}
CACHE_TTL = 30  # seconds


app = Flask(__name__)
app.secret_key = "supersecretkey"

FELLOWS_CSV = "Fellow Details _ School + Login - Sheet1.csv"
EVENTS_CSV = "Event List - Sheet2.csv"
SHEET_NAME = "CSK Student Event Registrations"

# ---------- GOOGLE SHEET ----------
def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    if "GOOGLE_CREDS" in os.environ:
        creds_dict = json.loads(os.environ["GOOGLE_CREDS"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)

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


def read_latest_students_for_user(user_email):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDS"]),
        scopes=scopes
    )

    client = gspread.authorize(creds)
    sheet = client.open("CSK Student Event Registrations").sheet1
    rows = sheet.get_all_records()

    latest = {}

    for r in rows:
        if r["Created By Email"] != user_email:
            continue

        name = r["Student Name"]
        action = r["Action"]

        ts = datetime.strptime(r["Timestamp"], "%d-%m-%Y %H:%M")

        if name not in latest or ts > latest[name]["_ts"]:
            r["_ts"] = ts
            latest[name] = r

    # 🚨 REMOVE deleted students
    final_students = [
        r for r in latest.values()
        if r["Action"] != "DELETED"
    ]

    return final_students



# ---------- LOADERS ----------
def load_fellows():
    fellows = {}
    with open(FELLOWS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fellows[row["Email"].strip()] = {
                "password": row["Password"].strip(),
                "school": row["School"].strip()
            }
    return fellows


def load_events():
    event_options = {}
    event_slot_map = {}

    with open(EVENTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            grade = row["Class"].strip()
            event = row["Event"].strip()

            slot1 = row["Time Slot 1"].strip()
            slot2 = row["Time Slot 2"].strip()

            event_options.setdefault(grade, {})
            for s in ["10-11am", "11-12pm", "1-2pm", "2-3pm"]:
                event_options[grade].setdefault(s, [])

            if slot1:
                event_options[grade][slot1].append(event)
            if slot2:
                event_options[grade][slot2].append(event)
                event_slot_map[event] = True

    for g in event_options:
        for s in event_options[g]:
            if "Not participating" not in event_options[g][s]:
                event_options[g][s].insert(0, "Not participating")

    return event_options, event_slot_map

def get_students_cached(user_email):
    now = time.time()

    if user_email in CACHE:
        data, ts = CACHE[user_email]
        if now - ts < CACHE_TTL:
            return data

    data = read_latest_students_for_user(user_email)
    CACHE[user_email] = (data, now)
    return data


EVENT_OPTIONS, EVENT_SLOT_MAP = load_events()


# ---------- AUTH ----------
@app.route("/", methods=["GET", "POST"])
def login():
    fellows = load_fellows()

    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"].strip()

        if email in fellows and fellows[email]["password"] == password:
            session["user_id"] = email
            session["school"] = fellows[email]["school"]
            return redirect(url_for("students"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- STUDENTS ----------
@app.route("/students")
def students():
    if "user_id" not in session:
        return redirect(url_for("login"))

    students = get_students_cached(session["user_id"])
    return render_template("students.html", students=students)


# ---------- REGISTER ----------
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
        return redirect(url_for("students"))

    return render_template(
        "register.html",
        event_options=EVENT_OPTIONS,
        event_slot_map=EVENT_SLOT_MAP
    )


# ---------- EDIT ----------
@app.route("/edit/<name>", methods=["GET", "POST"])
def edit_student(name):
    if "user_id" not in session:
        return redirect(url_for("login"))

    students = read_latest_students_for_user(session["user_id"])
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

        return redirect(url_for("students"))

    return render_template(
        "edit_student.html",
        student=student,
        event_options=EVENT_OPTIONS,
        event_slot_map=EVENT_SLOT_MAP
    )

# ---------- DELETE ----------
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

    return redirect(url_for("students"))


# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True)

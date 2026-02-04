from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import csv
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = "supersecretkey"

DATABASE = "database.db"
FELLOWS_CSV = "Fellow Details _ School + Login - Sheet1.csv"
EVENTS_CSV = "Event List - Sheet2.csv"


# ---------- HELPERS ----------
def write_to_google_sheet(data):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    if "GOOGLE_CREDS" in os.environ:
    creds_dict = json.loads(os.environ["GOOGLE_CREDS"])
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=scopes
        )
    else:
        creds = Credentials.from_service_account_file(
            "credentials.json",
            scopes=scopes
        )


    client = gspread.authorize(creds)
    sheet = client.open("CSK Student Event Registrations").sheet1

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




def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


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


# ---------- HOME: STUDENT LIST ----------

@app.route("/students")
def students():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM students
        WHERE created_by = ?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()
    conn.close()

    return render_template("students.html", students=rows)


# ---------- REGISTER NEW STUDENT ----------

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        conn = get_db()
        conn.execute("""
            INSERT INTO students
            (name, grade, section, school,
             event_10_11, event_11_12, event_1_2, event_2_3,
             created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["grade"],
            request.form["section"],
            session["school"],
            request.form["event_10_11"],
            request.form["event_11_12"],
            request.form["event_1_2"],
            request.form["event_2_3"],
            session["user_id"]
        ))
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


        conn.commit()
        conn.close()

        return redirect(url_for("students"))

    return render_template(
        "register.html",
        event_options=EVENT_OPTIONS,
        event_slot_map=EVENT_SLOT_MAP
    )


# ---------- EDIT ----------

@app.route("/edit/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            UPDATE students SET
            name=?, grade=?, section=?,
            event_10_11=?, event_11_12=?, event_1_2=?, event_2_3=?
            WHERE id=?
        """, (
            request.form["name"],
            request.form["grade"],
            request.form["section"],
            request.form["event_10_11"],
            request.form["event_11_12"],
            request.form["event_1_2"],
            request.form["event_2_3"],
            student_id
        ))
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


        conn.commit()
        conn.close()
        return redirect(url_for("students"))

    student = conn.execute(
        "SELECT * FROM students WHERE id=?",
        (student_id,)
    ).fetchone()
    conn.close()

    return render_template(
        "edit_student.html",
        student=student,
        event_options=EVENT_OPTIONS,
        event_slot_map=EVENT_SLOT_MAP
    )

# ---------- DELETE STUDENT -------------

@app.route("/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute(
        "DELETE FROM students WHERE id = ? AND created_by = ?",
        (student_id, session["user_id"])
    )
    conn.commit()
    conn.close()

    return redirect(url_for("students"))


# ---------- EVENT VIEW ----------

@app.route("/event-view")
def event_view():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    rows = conn.execute("""
        SELECT name, grade, section,
               event_10_11, event_11_12, event_1_2, event_2_3
        FROM students
        WHERE created_by = ?
    """, (session["user_id"],)).fetchall()
    conn.close()

    events = {}

    for r in rows:
        student = {
            "name": r["name"],
            "grade": r["grade"],
            "section": r["section"]
        }

        slots = {
            "10-11am": r["event_10_11"],
            "11-12pm": r["event_11_12"],
            "1-2pm": r["event_1_2"],
            "2-3pm": r["event_2_3"]
        }

        for slot, event in slots.items():
            if event and event != "Not participating":
                events.setdefault(event, {}).setdefault(slot, []).append(student)

    return render_template("event_view.html", events=events)


# ---------- RUN ----------

if __name__ == "__main__":
    app.run(debug=True)

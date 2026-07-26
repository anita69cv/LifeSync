from flask import Flask, render_template, request, redirect, send_from_directory
import os
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime, timedelta
from collections import Counter
import calendar
# Create the Flask application
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# -------------------- Reset Repeating Tasks --------------------

def reset_repeating_tasks():

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()

    today = datetime.today().date()
    today_str = today.isoformat()

    cursor.execute("""
        SELECT id, repeat_type, status, last_reset
        FROM tasks
        WHERE repeat_type IN ('Daily', 'Weekly', 'Monthly')
    """)

    tasks = cursor.fetchall()

    for task in tasks:

        task_id = task[0]
        repeat_type = task[1]
        last_reset = task[3]

        if last_reset is None:
            continue

        last_reset_date = datetime.strptime(
            last_reset,
            "%Y-%m-%d"
        ).date()

        should_reset = False

        if repeat_type == "Daily":
            should_reset = (today - last_reset_date).days >= 1

        elif repeat_type == "Weekly":
            should_reset = (today - last_reset_date).days >= 7

        elif repeat_type == "Monthly":
            should_reset = (today - last_reset_date).days >= 30

        if should_reset:

            cursor.execute("""
                UPDATE tasks
                SET status = 0,
                    last_reset = ?,
                    streak = 0
                WHERE id = ?
            """, (today_str, task_id))

    connection.commit()
    connection.close()

# -------------------- Home Page --------------------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/features")
def features():
    return render_template("features.html")

# -------------------- Login --------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        connection = sqlite3.connect("lifesync.db")
        cursor = connection.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        )

        user = cursor.fetchone()

        connection.close()

        if user:
            return redirect("/dashboard")
        else:
            return "<h2>❌ Invalid Email or Password!</h2>"

    return render_template("login.html")


# -------------------- Dashboard --------------------
@app.route("/dashboard")
def dashboard():

    reset_repeating_tasks()

    search = request.args.get("search", "")
    category = request.args.get("category", "")

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()

    # Search & Filter
    query = """
        SELECT id, task_name, category, repeat_type,
               status, goal, due_date, due_time, streak
        FROM tasks
        WHERE user_id = ?
    """

    params = [1]

    if search:
        query += " AND task_name LIKE ?"
        params.append("%" + search + "%")

    if category:
        query += " AND category = ?"
        params.append(category)

    cursor.execute(query, tuple(params))
    tasks = cursor.fetchall()

    # Due Date Status
    updated_tasks = []

    today = datetime.today().date()

    for task in tasks:

        due_date = task[6]

        if due_date:

            due = datetime.strptime(
                due_date,
                "%Y-%m-%d"
            ).date()

            if due < today:
                task_status = "🔴 Overdue"

            elif due == today:
                task_status = "🟡 Due Today"

            else:
                task_status = "🟢 Upcoming"

        else:
            task_status = ""

        updated_tasks.append(task + (task_status,))

    tasks = updated_tasks

    # Statistics

    cursor.execute(
        "SELECT COUNT(*) FROM tasks WHERE user_id = ?",
        (1,)
    )
    total_tasks = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 1",
        (1,)
    )
    completed_tasks = cursor.fetchone()[0]

    pending_tasks = total_tasks - completed_tasks

    if total_tasks > 0:
        progress = int((completed_tasks / total_tasks) * 100)
    else:
        progress = 0

    # Weekly Progress

    cursor.execute("""
        SELECT completed_date
        FROM tasks
        WHERE completed_date IS NOT NULL
        AND user_id = ?
    """, (1,))

    completed_dates = cursor.fetchall()

    weekly_count = Counter()

    for row in completed_dates:

        day = datetime.strptime(
            row[0],
            "%Y-%m-%d"
        ).strftime("%a")

        weekly_count[day] += 1

    weekly_data = [
        weekly_count["Mon"],
        weekly_count["Tue"],
        weekly_count["Wed"],
        weekly_count["Thu"],
        weekly_count["Fri"],
        weekly_count["Sat"],
        weekly_count["Sun"]
    ]

    connection.close()

    return render_template(
        "dashboard.html",
        tasks=tasks,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        progress=progress,
        weekly_data=weekly_data,
        search=search,
        category=category
    )

# -------------------- Add Task --------------------

@app.route("/add_task", methods=["GET", "POST"])
def add_task():

    if request.method == "POST":

        task_name = request.form["task_name"]
        category = request.form["category"]
        repeat_type = request.form["repeat_type"]
        goal = request.form["goal"]
        due_date = request.form["due_date"]
        due_time = request.form["due_time"]


        connection = sqlite3.connect("lifesync.db")
        cursor = connection.cursor()


        cursor.execute("""
            INSERT INTO tasks
                       (user_id, task_name, category, repeat_type, goal, due_date, due_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       """,
        (1, task_name, category, repeat_type, goal, due_date, due_time))


        connection.commit()
        connection.close()


        return redirect("/dashboard")


    return render_template("add_task.html")



# -------------------- Complete Task --------------------

@app.route("/complete_task/<int:task_id>")
def complete_task(task_id):

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()

    today = datetime.today().date().isoformat()

    cursor.execute("""
        UPDATE tasks
        SET status = 1,
            completed_date = ?,
            last_reset = ?,
            streak = CASE
                        WHEN status = 0 THEN streak + 1
                        ELSE streak
                     END
        WHERE id = ?
    """, (today, today, task_id))

    connection.commit()

    # Check if completed_date was saved
    cursor.execute("SELECT completed_date FROM tasks WHERE id = ?", (task_id,))
    print("Completed Date:", cursor.fetchone())

    connection.close()

    return redirect("/dashboard")



# -------------------- Delete Task --------------------

@app.route("/delete_task/<int:task_id>")
def delete_task(task_id):

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()


    cursor.execute(
        "DELETE FROM tasks WHERE id = ?",
        (task_id,)
    )


    connection.commit()
    connection.close()


    return redirect("/dashboard")



# -------------------- Edit Task --------------------

@app.route("/edit_task/<int:task_id>", methods=["GET", "POST"])
def edit_task(task_id):

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()


    if request.method == "POST":

        task_name = request.form["task_name"]
        category = request.form["category"]
        repeat_type = request.form["repeat_type"]
        goal = request.form["goal"]
        due_date = request.form["due_date"]
        due_time = request.form["due_time"]


        cursor.execute(
            """
            UPDATE tasks
SET task_name = ?,
    category = ?,
    repeat_type = ?,
    goal = ?,
    due_date = ?,
    due_time = ?
WHERE id = ?
            """,
            (
                task_name,
                category,
                repeat_type,
                goal,
                due_date,
                due_time,
                task_id
            )
        )


        connection.commit()
        connection.close()


        return redirect("/dashboard")



    cursor.execute(
        """
        SELECT task_name, category, repeat_type, goal, due_date, due_time
        FROM tasks
        WHERE id = ?
        """,
        (task_id,)
    )


    task = cursor.fetchone()


    connection.close()


    return render_template(
        "edit_task.html",
        task=task,
        task_id=task_id
    )



# -------------------- Register --------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]


        connection = sqlite3.connect("lifesync.db")
        cursor = connection.cursor()


        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (name, email, password)
        )


        connection.commit()
        connection.close()


        return redirect("/login")


    return render_template("register.html")



# -------------------- User Profile --------------------

@app.route("/profile")
def profile():

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()

    cursor.execute(
         "SELECT name, email, profile_image FROM users WHERE id = ?",
        (1,)
    )

    user = cursor.fetchone()


    cursor.execute(
        "SELECT COUNT(*) FROM tasks WHERE user_id = ?",
        (1,)
    )

    total_tasks = cursor.fetchone()[0]


    cursor.execute(
        "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 1",
        (1,)
    )

    completed_tasks = cursor.fetchone()[0]


    connection.close()


    return render_template(
        "profile.html",
        user=user,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks
    )

# -------------------- Edit Profile --------------------

@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]

        cursor.execute(
            """
            UPDATE users
            SET name = ?, email = ?
            WHERE id = ?
            """,
            (name, email, 1)
        )

        connection.commit()
        connection.close()

        return redirect("/profile")

    cursor.execute(
        """
        SELECT name, email
        FROM users
        WHERE id = ?
        """,
        (1,)
    )

    user = cursor.fetchone()

    connection.close()

    return render_template(
        "edit_profile.html",
        user=user
    )


# -------------------- Change Password --------------------

@app.route("/change_password", methods=["GET", "POST"])
def change_password():

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()

    if request.method == "POST":

        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        cursor.execute(
            "SELECT password FROM users WHERE id = ?",
            (1,)
        )

        stored_password = cursor.fetchone()[0]

        if current_password != stored_password:

            connection.close()

            return "<h2>❌ Current password is incorrect.</h2>"

        if new_password != confirm_password:

            connection.close()

            return "<h2>❌ New passwords do not match.</h2>"

        cursor.execute(
            """
            UPDATE users
            SET password = ?
            WHERE id = ?
            """,
            (new_password, 1)
        )

        connection.commit()
        connection.close()

        return redirect("/profile")

    connection.close()

    return render_template("change_password.html")

# -------------------- Serve Uploaded Images --------------------

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------- Upload Profile Picture --------------------

@app.route("/upload_profile_picture", methods=["POST"])
def upload_profile_picture():

    if "profile_image" not in request.files:
        return redirect("/profile")

    file = request.files["profile_image"]

    if file.filename == "":
        return redirect("/profile")

    filename = secure_filename(file.filename)

    file.save(
        os.path.join(app.config["UPLOAD_FOLDER"], filename)
    )

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET profile_image = ?
        WHERE id = ?
        """,
        (filename, 1)
    )

    connection.commit()
    connection.close()

    return redirect("/profile")

    # Add completed_date column (only once)

connection = sqlite3.connect("lifesync.db")
cursor = connection.cursor()

try:
    cursor.execute("ALTER TABLE tasks ADD COLUMN completed_date TEXT")
    connection.commit()
    print("completed_date column added.")
except sqlite3.OperationalError:
    print("completed_date column already exists.")

connection.close()

# -------------------- Calendar --------------------

@app.route("/calendar")
def calendar_page():

    today = datetime.today()

    year = today.year
    month = today.month

    cal = calendar.monthcalendar(year, month)

    connection = sqlite3.connect("lifesync.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT due_date, status
        FROM tasks
        WHERE user_id = ?
        AND due_date IS NOT NULL
    """, (1,))

    tasks = cursor.fetchall()

    connection.close()

    task_dates = {}

    for due_date, status in tasks:

        # Skip tasks with no due date
        if due_date:

            day = datetime.strptime(
                due_date,
                "%Y-%m-%d"
            ).day

            task_dates[day] = status

    return render_template(
        "calendar.html",
        calendar_data=cal,
        month=calendar.month_name[month],
        year=year,
        task_dates=task_dates
    )

# -------------------- Run Application --------------------

if __name__ == "__main__":
    app.run(debug=True)

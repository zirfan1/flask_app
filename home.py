from flask import Flask, render_template, request, jsonify, redirect
import pandas as pd
import sqlite3
import plotly.express as px

app = Flask(__name__)

# Load dataset
df = pd.read_csv("airline_delay.csv")

# Print actual column names for reference
print("CSV Columns:", df.columns.tolist())

# Ensure correct column selection
df = df[['year', 'month', 'carrier', 'carrier_name', 'airport', 'airport_name', 'arr_flights', 'arr_delay']]

# Convert columns to correct types
df['arr_delay'] = pd.to_numeric(df['arr_delay'], errors='coerce').fillna(0)
df['month'] = pd.to_numeric(df['month'], errors='coerce').fillna(0).astype(int)
df['year'] = pd.to_numeric(df['year'], errors='coerce').fillna(0).astype(int)

# Initialize SQLite Database
def init_db():
    conn = sqlite3.connect("feedback.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            airline TEXT NOT NULL,
            delay_rating INTEGER NOT NULL CHECK(delay_rating BETWEEN 1 AND 10)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Function to Process Monthly Data
def process_monthly_data():
    monthly_avg = df.groupby(['year', 'month'], as_index=False)['arr_delay'].mean()
    monthly_avg = monthly_avg.sort_values(by=['year', 'month'])
    return monthly_avg

# Home Page (Filters Flight Data)
@app.route("/", methods=["GET"])
def home():
    airline_filter = request.args.get("airline", "")
    origin_filter = request.args.get("origin", "")

    filtered_df = df.copy()
    if airline_filter:
        filtered_df = filtered_df[filtered_df["carrier_name"].str.contains(airline_filter, case=False, na=False)]
    if origin_filter:
        filtered_df = filtered_df[filtered_df["airport_name"].str.contains(origin_filter, case=False, na=False)]

    flight_data = filtered_df.head(10).to_html(classes="table table-striped")
    return render_template("index.html", table=flight_data)

# Delay Analysis Page
@app.route("/delay_analysis")
def delay_analysis():
    longest_delays = df.sort_values(by="arr_delay", ascending=False).head(10)
    avg_delays = df.groupby("carrier_name")["arr_delay"].mean().sort_values(ascending=False)

    fig = px.bar(avg_delays.reset_index(), x="carrier_name", y="arr_delay", title="Average Airline Delay")
    fig.write_html("static/delay_chart.html")

    return render_template("delay_analysis.html", table=longest_delays.to_html(classes="table table-striped"), image="static/delay_chart.html")

# Interactive Bar Chart
@app.route("/interactive_chart")
def interactive_chart():
    avg_delays = df.groupby("carrier_name")["arr_delay"].mean().sort_values(ascending=False).reset_index()
    fig = px.bar(avg_delays, x="carrier_name", y="arr_delay", title="Interactive Airline Delay Chart")
    return jsonify(fig.to_json())

# Line Chart (Monthly Flight Delays)
@app.route("/line_chart")
def line_chart():
    monthly_avg = process_monthly_data()

    if monthly_avg.empty:
        return jsonify({"error": "No data available"})

    monthly_avg["month"] = monthly_avg["month"].astype(str)
    monthly_avg["year"] = monthly_avg["year"].astype(str)

    fig = px.line(
        monthly_avg, 
        x="month", 
        y="arr_delay", 
        color="year",  
        markers=True,
        title="Monthly Flight Delay Trends"
    )
    return jsonify(fig.to_json())

# Store User Feedback in Database
@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    name = request.form.get("name")
    airline = request.form.get("airline")
    delay_rating = request.form.get("delay_rating")

    if not name or not airline or not delay_rating.isdigit():
        return jsonify({"error": "Invalid input"}), 400

    conn = sqlite3.connect("feedback.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO feedback (name, airline, delay_rating) VALUES (?, ?, ?)", 
                   (name, airline, int(delay_rating)))
    conn.commit()
    conn.close()

    return redirect("/feedback_summary")

# Show Summary of User Feedback
@app.route("/feedback_summary")
def feedback_summary():
    conn = sqlite3.connect("feedback.db")
    df_feedback = pd.read_sql_query("SELECT airline, AVG(delay_rating) as avg_rating FROM feedback GROUP BY airline", conn)
    conn.close()

    if df_feedback.empty:
        summary_table = "<p>No feedback available yet.</p>"
    else:
        summary_table = df_feedback.to_html(classes="table table-striped", index=False)

    return render_template("feedback.html", table=summary_table)

# Flight Recommendations Based on Feedback
@app.route("/recommendations")
def recommendations():
    conn = sqlite3.connect("feedback.db")
    df_feedback = pd.read_sql_query("SELECT airline, AVG(delay_rating) as avg_rating FROM feedback GROUP BY airline ORDER BY avg_rating DESC", conn)
    conn.close()

    if df_feedback.empty:
        return render_template("recommendations.html", recommendations="No recommendations yet.")

    best_airlines = df_feedback[df_feedback["avg_rating"] >= 7]["airline"].tolist()
    worst_airlines = df_feedback[df_feedback["avg_rating"] < 4]["airline"].tolist()

    recommendations_text = f"""
    <h2>Recommended Airlines</h2>
    <p>The following airlines have high user ratings and are recommended:</p>
    <ul>{''.join(f'<li>{airline}</li>' for airline in best_airlines) if best_airlines else '<li>No top-rated airlines yet</li>'}</ul>

    <h2>Airlines with Frequent Delays</h2>
    <p>These airlines have received lower user ratings due to frequent delays:</p>
    <ul>{''.join(f'<li>{airline}</li>' for airline in worst_airlines) if worst_airlines else '<li>No low-rated airlines yet</li>'}</ul>
    """

    return render_template("recommendations.html", recommendations=recommendations_text)

if __name__ == "__main__":
    app.run(debug=True)

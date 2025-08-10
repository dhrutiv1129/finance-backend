from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import re  # needed for parsing income strings

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins for all routes

# Median annual incomes by age range (USD)
MEDIAN_INCOME_BY_AGE = {
    "Under 20": 20000,
    "20 - 29": 35000,
    "30 - 39": 55000,
    "40 - 49": 70000,
    "50 - 59": 75000,
    "60 - 69": 65000,
    "70 - 79": 50000,
    "80 - 89": 40000,
    "90 and above": 30000
}

# Parse monthly income range strings like "Under $1,000", "$1,000 - $2,499", "$10,000+"
def parse_monthly_income(income_str):
    if not income_str:
        return None

    income_str = income_str.replace(",", "").replace("$", "").strip()

    # Under X (e.g. "Under 1000")
    if income_str.lower().startswith("under"):
        match = re.search(r"Under\s*(\d+)", income_str, re.IGNORECASE)
        if match:
            return float(match.group(1)) * 0.5  # estimate half of upper bound

    # Range X - Y (e.g. "1000 - 2499")
    if "-" in income_str:
        parts = income_str.split("-")
        try:
            low = float(parts[0].strip())
            high = float(parts[1].strip())
            return (low + high) / 2  # midpoint estimate
        except:
            return None

    # X+ (e.g. "10000+")
    if income_str.endswith("+"):
        try:
            num = float(income_str[:-1].strip())
            return num  # use lower bound
        except:
            return None

    # fallback
    try:
        return float(income_str)
    except:
        return None

def income_score(age, annual_income):
    median = MEDIAN_INCOME_BY_AGE.get(age)
    if median is None or median == 0:
        return 6  # Neutral default score
    ratio = annual_income / median
    if ratio < 0.5:
        return 1
    elif ratio > 1.5:
        return 10
    else:
        return round(1 + (ratio - 0.5) * 9, 2)

@app.route('/process-assessment', methods=['POST'])
def process_assessment():
    data = request.get_json()
    age = data.get("age")
    monthly_income_str = data.get("monthlyIncome")

    if not age or not monthly_income_str:
        return jsonify({"error": "Missing required fields: age or monthlyIncome"}), 400

    monthly_income = parse_monthly_income(monthly_income_str)
    if monthly_income is None:
        return jsonify({"error": "Could not parse monthlyIncome"}), 400

    annual_income = monthly_income * 12
    score = income_score(age, annual_income)

    return jsonify({
        "incomeScore": score,
        "overallScore": score,
        "receivedData": data
    })

@app.route('/')
def home():
    return "Backend is running!"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import re

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

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

DEPENDENT_PERCENT_PENALTY = {
    "0%": 1.0,         # no penalty
    "1-10%": 0.95,
    "11-25%": 0.85,
    "26-50%": 0.70,
    "51-75%": 0.50,
    "76-100%": 0.30
}

def parse_monthly_income(income_str):
    if not income_str:
        return None

    income_str = income_str.replace(",", "").replace("$", "").strip()

    if income_str.lower().startswith("under"):
        match = re.search(r"Under\s*(\d+)", income_str, re.IGNORECASE)
        if match:
            return float(match.group(1)) * 0.5

    if "-" in income_str:
        parts = income_str.split("-")
        try:
            low = float(parts[0].strip())
            high = float(parts[1].strip())
            return (low + high) / 2
        except:
            return None

    if income_str.endswith("+"):
        try:
            num = float(income_str[:-1].strip())
            return num
        except:
            return None

    try:
        return float(income_str)
    except:
        return None

def income_score(age, annual_income, income_percent_to_dependents):
    median = MEDIAN_INCOME_BY_AGE.get(age)
    if median is None or median == 0:
        base_score = 6
    else:
        ratio = annual_income / median
        if ratio < 0.5:
            base_score = 1
        elif ratio > 1.5:
            base_score = 10
        else:
            base_score = round(1 + (ratio - 0.5) * 9, 2)

    # Apply dependent penalty factor
    penalty_factor = DEPENDENT_PERCENT_PENALTY.get(income_percent_to_dependents, 1.0)
    adjusted_score = round(base_score * penalty_factor, 2)

    return max(1, min(10, adjusted_score))  # clamp between 1 and 10

@app.route('/process-assessment', methods=['POST'])
def process_assessment():
    data = request.get_json()
    age = data.get("age")
    monthly_income_str = data.get("monthlyIncome")
    income_percent_to_dependents = data.get("incomeToDependentsPercent")

    if not age or not monthly_income_str:
        return jsonify({"error": "Missing required fields: age or monthlyIncome"}), 400

    monthly_income = parse_monthly_income(monthly_income_str)
    if monthly_income is None:
        return jsonify({"error": "Could not parse monthlyIncome"}), 400

    annual_income = monthly_income * 12
    score = income_score(age, annual_income, income_percent_to_dependents)

    return jsonify({
        "incomeScore": score,
        "overallScore": score,  # later you could merge with other section scores
        "receivedData": data
    })

@app.route('/')
def home():
    return "Backend is running!"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)

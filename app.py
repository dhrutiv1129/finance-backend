from flask import Flask, request, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes by default

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
        return round(1 + (ratio - 0.5) * 9, 2)  # linear scaling between 0.5x and 1.5x

@app.route('/process-assessment', methods=['POST'])
def process_assessment():
    data = request.get_json()
    age = data.get("age")  # string like "20 - 29"
    monthly_income = data.get("monthlyIncome")  # number or string

    if not age or monthly_income is None:
        return jsonify({"error": "Missing required fields: age or monthlyIncome"}), 400

    try:
        monthly_income = float(monthly_income)
    except ValueError:
        return jsonify({"error": "monthlyIncome must be numeric"}), 400

    # Convert monthly income to annual
    annual_income = monthly_income * 12
    score = income_score(age, annual_income)

    return jsonify({
        "incomeScore": score,
        "overallScore": score,  # overall score is just the income score now
        "receivedData": data
    })

@app.route('/')
def home():
    return "Backend is running!"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

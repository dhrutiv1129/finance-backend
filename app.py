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
    "0%": 1.0,
    "1-10%": 0.95,
    "11-25%": 0.85,
    "26-50%": 0.70,
    "51-75%": 0.50,
    "76-100%": 0.30
}

FAMILY_BUDGET_MAPPING = {
    "Under $1,000": 10,
    "$1,000 - $2,499": 8,
    "$2,500 - $4,999": 6,
    "$5,000 - $7,499": 5,
    "$7,500 - $9,999": 3,
    "$10,000+": 1
}

ASSET_MAPPING = {
    "Less than $100,000": 1,
    "$100,000 - $500,000": 3,
    "$500,000 - $1,000,000": 5,
    "$1,000,000 - $2,000,000": 7,
    "$2,000,000 - $5,000,000": 9,
    "Greater than $5,000,000": 10
}

DEBT_MAPPING = {
    "Less than $100,000": 10,
    "$100,000 - $500,000": 8,
    "$500,000 - $1,000,000": 6,
    "$1,000,000 - $2,000,000": 4,
    "$2,000,000 - $5,000,000": 2,
    "Greater than $5,000,000": 1
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
            return float(income_str[:-1].strip())
        except:
            return None
    try:
        return float(income_str)
    except:
        return None


def income_score(age, monthly_income, income_percent_to_dependents):
    median = MEDIAN_INCOME_BY_AGE.get(age)
    if median is None or median == 0:
        base_score = 6
    else:
        annual_income = monthly_income * 12
        ratio = annual_income / median
        if ratio < 0.5:
            base_score = 1
        elif ratio > 1.5:
            base_score = 10
        else:
            base_score = round(1 + (ratio - 0.5) * 9, 2)
    penalty_factor = DEPENDENT_PERCENT_PENALTY.get(income_percent_to_dependents, 1.0)
    adjusted_score = round(base_score * penalty_factor, 2)
    return max(1, min(10, adjusted_score))


def family_budget_score(expense_range):
    return FAMILY_BUDGET_MAPPING.get(expense_range, 5)


def net_worth_score(assets, debt):
    asset_score = ASSET_MAPPING.get(assets, 5)
    debt_score = DEBT_MAPPING.get(debt, 5)
    return round((asset_score + debt_score) / 2, 1)


@app.route('/process-assessment', methods=['POST'])
def process_assessment():
    data = request.get_json()
    
    # Income
    age = data.get("age")
    monthly_income_str = data.get("familyGrossIncome")
    income_percent_to_dependents = data.get("incomeToDependentsPercent", "0%")
    
    if not age or not monthly_income_str:
        return jsonify({"error": "Missing required fields: age or familyGrossIncome"}), 400
    
    monthly_income = parse_monthly_income(monthly_income_str)
    if monthly_income is None:
        return jsonify({"error": "Could not parse familyGrossIncome"}), 400
    
    income_subscore = income_score(age, monthly_income, income_percent_to_dependents)
    
    # Family Budget
    family_expense = data.get("familyExpenses")
    family_budget_subscore = family_budget_score(family_expense)
    
    # Net Worth
    assets = data.get("totalAssets")
    debt = data.get("totalDebt")
    net_worth_subscore = net_worth_score(assets, debt)
    
    return jsonify({
        "incomeScore": income_subscore,
        "familyBudgetScore": family_budget_subscore,
        "netWorthScore": net_worth_subscore,
        "receivedData": data
    })


@app.route('/')
def home():
    return "Backend is running!"


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)

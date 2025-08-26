from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import os
import re
import pandas as pd

app = Flask(__name__)
CORS(app)  # allows all origins

# Load CSV
income_table = pd.read_csv("income_percentiles.csv")
income_table["income from"] = income_table["income from"].replace('[\$,]', '', regex=True).astype(float)
income_table["income to"] = income_table["income to"].replace('[\$,]', '', regex=True).astype(float)
income_table["Percentile"] = pd.to_numeric(income_table["Percentile"], errors="coerce")

print(income_table["income from"])

# Age mapping
AGE_GROUP_MAPPING = {
    "15 to 24 years": 1,
    "25 to 29 years": 2,
    "30 to 34 years": 3,
    "35 to 39 years": 4,
    "40 to 44 years": 5,
    "45 to 49 years": 6,
    "50 to 54 years": 7,
    "55 to 59 years": 8,
    "60 to 64 years": 9,
    "65 to 69 years": 10,
    "70 to 74 years": 11,
    "75 years and over": 12,
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
    "Less than $25,000": 1,
    "Less than $100,000": 2,
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


def parse_monthly_income(income):
    """Convert frontend input to a numeric monthly income."""
    if income is None:
        return None
    if isinstance(income, (int, float)):
        return float(income)
    if not isinstance(income, str):
        return None
    income_str = income.replace(",", "").replace("$", "").strip()
    try:
        return float(income_str)
    except:
        return None


def income_score(age_label, monthly_income):
    print(f"[DEBUG] income_score called with age={age_label}, income={monthly_income}") 
    age_group_id = AGE_GROUP_MAPPING.get(age_label)
    if age_group_id is None:
        return None
    age_data = income_table[income_table["age_group_id"] == age_group_id]
    row = age_data[
        (age_data["income from"] <= monthly_income) &
        (age_data["income to"] >= monthly_income)
    ]
    if row.empty:
        return None
    print(f"[DEBUG] Age: {age_group_id}, Percentile: {row.iloc[0]['Percentile']}")

    return row.iloc[0]["Percentile"] * 10  # numeric score


def family_budget_score(expense_range):
    return FAMILY_BUDGET_MAPPING.get(expense_range, 5)


def net_worth_score(assets, debt):
    asset_score = ASSET_MAPPING.get(assets, 5)
    debt_score = DEBT_MAPPING.get(debt, 5)
    return round((asset_score + debt_score) / 2, 1)


@app.route('/process-assessment', methods=['POST'])
@cross_origin()
def process_assessment():
    data = request.get_json()

    # Age
    age_input = data.get("age")
    if age_input is None:
        return jsonify({"error": "Invalid age input"}), 400

    # Income
    family_gross_income = parse_monthly_income(data.get("familyGrossIncome")) or 30000

    # Calculate scores
    income_subscore = income_score(age_input, family_gross_income)
    print("income subscore:", income_subscore)
    family_budget_subscore = family_budget_score(data.get("familyExpenses"))
    net_worth_subscore = net_worth_score(data.get("totalAssets"), data.get("totalDebt"))

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

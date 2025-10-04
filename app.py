from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import os
import re
import pandas as pd
import math

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ===============================
# 📊 Load and prepare CSV data
# ===============================
income_table = pd.read_csv("income_percentiles.csv")
income_table["income from"] = income_table["income from"].replace('[\$,]', '', regex=True).astype(float)
income_table["income to"] = income_table["income to"].replace('[\$,]', '', regex=True).astype(float)
income_table["Percentile"] = pd.to_numeric(income_table["Percentile"], errors="coerce")
networth_percentile = pd.read_csv("networth_percentile.csv")

median_incomes = (
    income_table[income_table["Percentile"] <= 0.50]
    .sort_values(["age_group_id", "Percentile"])
    .groupby("age_group_id")
    .tail(1)
)
median_incomes["default_income"] = (
    ((median_incomes["income from"] + median_incomes["income to"]) / 2)
    .round(-3)
    .astype(int)
)

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

FAMILY_BUDGET_MAPPING = {
    "Under $1,000": 10,
    "$1,000 - $2,499": 8,
    "$2,500 - $4,999": 6,
    "$5,000 - $7,499": 5,
    "$7,500 - $9,999": 3,
    "$10,000+": 1
}

# ===============================
# 🧮 Utility Functions
# ===============================
def parse_range_to_midpoint(range_str: str) -> float:
    """Convert a string range into its midpoint value."""
    if not isinstance(range_str, str):
        return 0
    range_str = range_str.replace(",", "").strip()

    if range_str.startswith("Under") or "Less than" in range_str:
        num = int(re.findall(r"\d+", range_str)[0])
        return num / 2
    elif "Greater than" in range_str:
        num = int(re.findall(r"\d+", range_str)[0])
        return num * 1.5
    else:
        nums = list(map(int, re.findall(r"\d+", range_str)))
        if len(nums) == 2:
            return (nums[0] + nums[1]) / 2
        elif len(nums) == 1:
            return nums[0]
        else:
            return 0

# ===============================
# 💵 Income Score
# ===============================
def income_score(age_label, monthly_income):
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
    return row.iloc[0]["Percentile"] * 10

# ===============================
# 💰 Family Budget Score
# ===============================
def family_budget_score(expense_range):
    return FAMILY_BUDGET_MAPPING.get(expense_range, 5)

# ===============================
# 💵 Net Worth Score Helpers
# ===============================
NET_WORTH_RANGES = {
    1: (float("-inf"), 25000),
    2: (26000, 100000),
    3: (101000, 500000),
    4: (501000, 1000000),
    5: (1000001, 2000000),
    6: (2000001, 5000000),
    7: (5000001, float("inf")),
}

def map_networth_to_range_id(networth: float) -> int:
    for range_id, (low, high) in NET_WORTH_RANGES.items():
        if low <= networth <= high:
            return range_id
    return 7

def compute_networth_subscore(age_label, total_assets_str, total_debt_str):
    try:
        assets_val = parse_range_to_midpoint(total_assets_str)
        debt_val = parse_range_to_midpoint(total_debt_str)
        net_worth = assets_val - debt_val
        networth_range_id = map_networth_to_range_id(net_worth)
        age_group_id = AGE_GROUP_MAPPING.get(age_label)
        if age_group_id is None:
            return 0
        row = networth_percentile[
            (networth_percentile["age_group_id"] == age_group_id) &
            (networth_percentile["net_worth_group_id"] == networth_range_id)
        ]
        if row.empty:
            return 0
        percentile = row.iloc[0]["percentile_value"] * 100
        return percentile / 10
    except Exception as e:
        print("Error computing networth_subscore:", e)
        return 0

# ===============================
# 🧓 Retirement Projection Logic
# ===============================
def get_target_ar(age_label):
    target_table = {
        25: 0.2,
        30: 0.6,
        35: 1.0,
        40: 1.8,
        45: 3.0,
        50: 4.5,
        55: 6.0,
        60: 8.0,
        65: 10.0,
    }
    age_match = re.findall(r"\d+", age_label)
    if not age_match:
        return 3.0
    numeric_age = int(age_match[0])
    closest = min(target_table.keys(), key=lambda x: abs(x - numeric_age))
    return target_table[closest]

def map_strategy_to_return(strategy):
    mapping = {
        "Aggressive": 0.08,
        "Moderate": 0.05,
        "Conservative": 0.03,
    }
    return mapping.get(strategy, 0.04)

def get_retirement_score_ratio(ratio):
    """Smoothly convert projected/target ratio into a 1–10 score."""
    if ratio <= 0:
        return 1
    midpoint = 1.0
    steepness = 3.5
    score = 1 + 9 / (1 + math.exp(-steepness * (ratio - midpoint)))
    return round(score, 1)

def calculate_retirement_projection(data):
    """Estimate retirement readiness and return ratio + score."""
    try:
        age_label = data.get("age")
        total_assets_str = data.get("totalAssets")
        total_debt_str = data.get("totalDebt")
        strategy = data.get("investmentStrategy", "Moderate")
        monthly_expenses_str = data.get("familyExpenses", "$2,500 - $4,999")

        # Convert strings to numbers
        assets_val = parse_range_to_midpoint(total_assets_str)
        debt_val = parse_range_to_midpoint(total_debt_str)
        monthly_expenses = parse_range_to_midpoint(monthly_expenses_str)
        annual_expenses = monthly_expenses * 12

        # Compute actual asset ratio
        net_worth = max(assets_val - debt_val, 0)
        projected_ar = net_worth / annual_expenses if annual_expenses > 0 else 0

        # Compute target & return-based projections
        target_ar = get_target_ar(age_label)
        expected_return = map_strategy_to_return(strategy)

        # Roughly project 10 years forward with compounding
        projected_future = net_worth * ((1 + expected_return) ** 10)
        future_ratio = projected_future / (annual_expenses * target_ar)

        # Score based on how close projected ratio is to target
        score = get_retirement_score_ratio(future_ratio)

        return {
            "current_ratio": round(projected_ar, 2),
            "target_ratio": target_ar,
            "future_ratio": round(future_ratio, 2),
            "retirement_score": score  # ✅ always defined
        }

    except Exception as e:
        print("❌ Error in calculate_retirement_projection:", e)
        return {
            "current_ratio": 0,
            "target_ratio": 0,
            "future_ratio": 0,
            "retirement_score": 1  # ✅ fallback score
        }


# ===============================
# 🚀 API Endpoints
# ===============================
@app.route("/process-assessment", methods=["POST"])
@cross_origin()
def process_assessment():
    data = request.get_json()
    age_input = data.get("age")
    if not age_input:
        return jsonify({"error": "Invalid age input"}), 400

    family_gross_income = data.get("familyGrossIncome")
    try:
        family_gross_income = float(family_gross_income)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid familyGrossIncome"}), 400

    total_assets = data.get("totalAssets")
    total_debt = data.get("totalDebt")
    if not total_assets or not total_debt:
        return jsonify({"error": "Missing totalAssets or totalDebt"}), 400

    income_subscore = income_score(age_input, family_gross_income)
    family_budget_subscore = family_budget_score(data.get("familyExpenses"))
    net_worth_subscore = compute_networth_subscore(age_input, total_assets, total_debt)
    retirement_data = calculate_retirement_projection(data)

    return jsonify({
        "incomeScore": income_subscore,
        "familyBudgetScore": family_budget_subscore,
        "netWorthScore": net_worth_subscore,
        "retirementProjection": retirement_data,
        "receivedData": data
    })

@app.route('/')
def home():
    return "Backend is running!"

# ===============================
# 🔥 Run the App
# ===============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)

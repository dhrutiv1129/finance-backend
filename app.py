from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import os
import re
import pandas as pd



app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


app = Flask(__name__)
CORS(app)  # allows all origins

# Load CSV
income_table = pd.read_csv("income_percentiles.csv")
income_table["income from"] = income_table["income from"].replace('[\$,]', '', regex=True).astype(float)
income_table["income to"] = income_table["income to"].replace('[\$,]', '', regex=True).astype(float)
income_table["Percentile"] = pd.to_numeric(income_table["Percentile"], errors="coerce")
networth_percentile = pd.read_csv("networth_percentile.csv")


print(income_table)
median_incomes = (
    income_table[income_table["Percentile"] <= 0.50]  # only keep <= 0.50
    .sort_values(["age_group_id", "Percentile"])      # sort within groups
    .groupby("age_group_id")                          # group by age group
    .tail(1)                                          # take the closest (max ≤ 0.50)
)
median_incomes["default_income"] = (
    ((median_incomes["income from"] + median_incomes["income to"]) / 2).round(-3).astype(int)
)

print(median_incomes)
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


def parse_range_to_midpoint(range_str: str) -> float:
    """Convert a string range into its midpoint value."""
    range_str = range_str.replace(",", "").strip()

    if range_str.startswith("Under"):
        # Example: "Under $25,000"
        num = int(re.findall(r"\d+", range_str)[0])
        return num / 2  # midpoint below threshold

    elif "Less than" in range_str:
        # Example: "Less than $25,000"
        num = int(re.findall(r"\d+", range_str)[0])
        return num / 2  # midpoint below threshold

    elif "Greater than" in range_str:
        # Example: "Greater than $5,000,000"
        num = int(re.findall(r"\d+", range_str)[0])
        return num * 1.5  # arbitrary extension above threshold

    else:
        # Example: "$101,000 - $500,000"
        nums = list(map(int, re.findall(r"\d+", range_str)))
        if len(nums) == 2:
            return (nums[0] + nums[1]) / 2
        else:
            raise ValueError(f"Invalid range format: {range_str}")



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
   

    return row.iloc[0]["Percentile"] * 100  # numeric score



@app.route("/income-percentile", methods=["POST"])
@cross_origin()
def get_income_percentile():
    data = request.get_json()
    age_input = data.get("age")
    income = data.get("income")

    if not age_input or income is None:
        return jsonify({"error": "Missing required fields"}), 400

    # Map to age group id
    age_group_id = AGE_GROUP_MAPPING.get(age_input)
    if age_group_id is None:
        return jsonify({"incomePercentile": None})

    # Filter income table for that age group
    age_data = income_table[income_table["age_group_id"] == age_group_id]
    row = age_data[
        (age_data["income from"] <= float(income)) &
        (age_data["income to"] >= float(income))
    ]

    if row.empty:
        return jsonify({"incomePercentile": None})

    percentile = row.iloc[0]["Percentile"] * 100
    return jsonify({"incomePercentile": percentile})



def family_budget_score(expense_range):
    return FAMILY_BUDGET_MAPPING.get(expense_range, 5)


def net_worth_score(assets, debt):
    asset_score = ASSET_MAPPING.get(assets, 5)
    debt_score = DEBT_MAPPING.get(debt, 5)
    return round((asset_score + debt_score) / 2, 1)

# Define ranges explicitly (midpoints handled in parse_range_to_midpoint)
NET_WORTH_RANGES = {
    1: (0, 25000),
    2: (26000, 100000),
    3: (101000, 500000),
    4: (501000, 1000000),
    5: (1000001, 2000000),
    6: (2000001, 5000000),
    7: (5000001, float("inf")),
}

def map_networth_to_range_id(networth: float) -> int:
    """Map numeric net worth into a defined range bucket."""
    for range_id, (low, high) in NET_WORTH_RANGES.items():
        if low <= networth <= high:
            return range_id
    return 7  # default to the top bucket if somehow above all ranges


@app.route("/networth-percentile", methods=["POST"])
@cross_origin()
def get_networth_percentile():
    data = request.get_json()
    age_input = data.get("age")
    assets = data.get("totalAssets")
    debt = data.get("totalDebt")

    if not age_input or assets is None or debt is None:
        return jsonify({"error": "Missing required fields"}), 400

    # Compute numeric net worth
    asset_val = parse_range_to_midpoint(assets)
    debt_val = parse_range_to_midpoint(debt)
    net_worth = asset_val - debt_val

    # Map to net worth range
    networth_range_id = map_networth_to_range_id(net_worth)

    # Get percentile from precomputed table
    age_group_id = AGE_GROUP_MAPPING.get(age_input)
    if age_group_id is None:
        return jsonify({"networthPercentile": None})

    row = networth_percentile[
        (networth_percentile["age_group_id"] == age_group_id) &
        (networth_percentile["net_worth_group_id"] == networth_range_id)
    ]

    if row.empty:
        return jsonify({"networthPercentile": None})
    percentile = row.iloc[0]["percentile_value"] * 100
    return jsonify({"networthPercentile": percentile})


@app.route('/default-income', methods=['POST'])
@cross_origin()
def default_income():
    print("hello")
    data = request.get_json()
    age_input = data.get("age")
    if age_input is None:
        return jsonify({"error": "Invalid age input"}), 400

    # Get mapped age group id
    age_group_id = AGE_GROUP_MAPPING.get(age_input)
    if age_group_id is None:
        return jsonify({"defaultIncome": 40000})  # fallback

    # Look up the precomputed default income from median_incomes
    row = median_incomes[median_incomes["age_group_id"] == age_group_id]
    if row.empty:
        return jsonify({"defaultIncome": 50000})  # fallback

    default_income_val = row.iloc[0]["default_income"]
    return jsonify({"defaultIncome": default_income_val})




@app.route('/process-assessment', methods=['POST'])
@cross_origin()
def process_assessment():
    data = request.get_json()

    # Age
    age_input = data.get("age")
    if age_input is None:
        return jsonify({"error": "Invalid age input"}), 400

    # Income
    family_gross_income = data.get("familyGrossIncome")


    # Calculate scores
    income_subscore = income_score(age_input, family_gross_income)
    
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
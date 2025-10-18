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



median_incomes = (
    income_table[income_table["Percentile"] <= 0.50]  # only keep <= 0.50
    .sort_values(["age_group_id", "Percentile"])      # sort within groups
    .groupby("age_group_id")                          # group by age group
    .tail(1)                                          # take the closest (max ≤ 0.50)
)
median_incomes["default_income"] = (
    ((median_incomes["income from"] + median_incomes["income to"]) / 2).round(-3).astype(int)
)

print("hello")
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

def safe_int(val, default):
    try:
        return int(float(str(val).replace(",", "").strip()))
    except Exception:
        return default

def safe_float(val, default):
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except Exception:
        return default


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





def net_worth_score(assets, debt):
    asset_score = ASSET_MAPPING.get(assets, 5)
    debt_score = DEBT_MAPPING.get(debt, 5)
    return round((asset_score + debt_score) / 2, 1)

# Define ranges explicitly (midpoints handled in parse_range_to_midpoint)
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
    """Map numeric net worth into a defined range bucket."""
    for range_id, (low, high) in NET_WORTH_RANGES.items():
        if low <= networth <= high:
            return range_id
    return 7  # default to the top bucket if somehow above all ranges


@app.route("/networth-percentile", methods=["POST"])
@cross_origin()
def get_networth_percentile():
    print("hello")

    data = request.get_json()
    print("\n--- /networth-percentile request ---")
    print("Raw request data:", data)

    age_input = data.get("age")
    assets = data.get("totalAssets")
    debt = data.get("totalDebt")
    print("Parsed inputs -> age:", age_input, "| assets:", assets, "| debt:", debt)

    if not age_input or assets is None or debt is None:
        print("❌ Missing required fields")
        return jsonify({"error": "Missing required fields"}), 400

    # Compute numeric net worth
    asset_val = parse_range_to_midpoint(assets)
    debt_val = parse_range_to_midpoint(debt)
    net_worth = asset_val - debt_val
    print(f"Converted -> asset_val={asset_val}, debt_val={debt_val}, net_worth={net_worth}")

    # Map to net worth range
    networth_range_id = map_networth_to_range_id(net_worth)
    print("Mapped networth_range_id:", networth_range_id)

    # Get age group id
    age_group_id = AGE_GROUP_MAPPING.get(age_input)
    print("Age group id:", age_group_id)
    if age_group_id is None:
        print("❌ Age not found in AGE_GROUP_MAPPING")
        return jsonify({"networthPercentile": None})

    # Get row from CSV
    row = networth_percentile[
        (networth_percentile["age_group_id"] == age_group_id) &
        (networth_percentile["net_worth_group_id"] == networth_range_id)
    ]
    print("Filtered row from CSV:")
    print(row)

    if row.empty:
        print("❌ No matching row found in networth_percentile.csv")
        return jsonify({"networthPercentile": None})

    percentile = row.iloc[0]["percentile_value"] * 100
    print("Final percentile (×100):", percentile)

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


def age_label_to_number(age_label: str) -> int:
    """Convert age range label into a representative numeric age."""
    mapping = {
        "15 to 24 years": 20,
        "25 to 29 years": 27,
        "30 to 34 years": 32,
        "35 to 39 years": 37,
        "40 to 44 years": 42,
        "45 to 49 years": 47,
        "50 to 54 years": 52,
        "55 to 59 years": 57,
        "60 to 64 years": 62,
        "65 to 69 years": 67,
        "70 to 74 years": 72,
        "75 years and over": 78,
    }
    return mapping.get(age_label, 30)  # default 30

def default_retirement_age(current_age):
    """Compute default retirement age based on current age."""
    if current_age > 60:
        # Round up to nearest multiple of 5
        return ((current_age + 4) // 5) * 5
    return 60

def calculate_fam_budget_score(data):
    annualExpenses = parse_range_to_midpoint(data.get("familyExpenses", "$50,000 - $100,000")) * 12
    familyGrossIncome = safe_float(data.get("familyGrossIncome"), 60000)
    ratio = familyGrossIncome / annualExpenses
    print("fam: ", ratio)
    mapping = [
        (1, 1),
        (1.5, 2),
        (2, 3),
        (2.5, 4),
        (3, 5),
        (3.5, 6),
        (4, 7),
    ]
    if(ratio >= 5):
        return 10
    else:
        for (threshold, score) in mapping:
            if (ratio < threshold):
                return score
            
            
            
        
        
    


def calculate_retirement_score(data):
    """Compute user's retirement readiness score (1–10 scale) based on AR and target AR tables."""

    try:
        # ---- Step 1: Parse inputs ----
        current_age = age_label_to_number(data.get("age"))
        retirement_age = safe_int(data.get("retirementAge"), 65)
        annual_expenses = parse_range_to_midpoint(data.get("familyExpenses", "$50,000 - $100,000")) * 12
        assets = parse_range_to_midpoint(data.get("retirementAccountValue", "$100,000 - $500,000"))

        strategy = data.get("retirementStrategy", "Moderate")
        expense_change = data.get("postRetirementExpenses", "Same")

        # ---- Step 2: Constants ----
        RATES = {"Conservative": 0.05, "Moderate": 0.08, "Aggressive": 0.12}
        MULTIPLIER = {"Same": 1.0, "Lower": 0.8, "Higher": 1.3}

        R = RATES.get(strategy, 0.08)
        M = MULTIPLIER.get(expense_change, 1.0)

        # ---- Step 3: Years until and after retirement ----
        
        Y1 = max(retirement_age - current_age, 0) 
        print("till retirement", Y1)    # years until retirement
        Y = max(95 - retirement_age, 0)     
        print("years after retirement", Y)          # years after retirement

        # ---- Step 4: Compute Future Assets (FA) and Future Expenses (FE) ----
        
        print("assets")
        print(assets)
        print("R")
        print(R)

        

        FA = assets * ((1 + R) ** Y1)
        print("future assets", FA)
        FE = annual_expenses * M * Y
        print("future expenses", FE)

        if FE <= 0:
            return 1  # fail-safe

        projected_AR = (FA / FE) / 10
        print("projected ar", projected_AR)

        # ---- Step 5: Target AR based on current age ----
        target_AR_table = {
            25: 0.05, 30: 0.10, 35: 0.20, 40: 0.35,
            45: 0.50, 50: 0.70, 55: 1.00, 60: 1.30, 65: 1.50,
        }
        target_values = [val for age, val in target_AR_table.items() if current_age >= age]
        target_AR = max(target_values) if target_values else 0.05  # default for young users
        print("target ar", target_AR)


        # ---- Step 6: Retirement Ratio ----
        retirement_ratio = projected_AR / target_AR
        print("Retirement Ratio:", retirement_ratio)

        # ---- Step 7: Map ratio → 1–10 score ----
        thresholds = [
            (0.1, 1),
            (0.2, 2),
            (0.3, 3),
            (0.4, 4),
            (0.5, 5),
            (0.6, 6),
            (0.7, 7),
            (0.8, 8),
            (0.9, 9),
            (1, 10),
        ]

        retirement_score = 10  # default if above highest threshold
        for threshold, score in thresholds:
            if retirement_ratio < threshold:
                retirement_score = score
                break

        return round(retirement_score, 1)

    except Exception as e:
        print("Error computing retirement score:", e)
        return 1


@app.route('/process-assessment', methods=['POST'])
@cross_origin()
def process_assessment():
    data = request.get_json()

    # Age
    age_input = data.get("age")
    if not age_input:
        return jsonify({"error": "Invalid age input"}), 400

    # Income
    family_gross_income = data.get("familyGrossIncome")
    try:
        family_gross_income = float(family_gross_income)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid familyGrossIncome"}), 400

    # Assets/Debt
    total_assets = data.get("totalAssets")
    total_debt = data.get("totalDebt")
    if not total_assets or not total_debt:
        return jsonify({"error": "Missing totalAssets or totalDebt"}), 400

    # Calculate scores
    income_subscore = income_score(age_input, family_gross_income)
    print("going in")
    family_budget_subscore = calculate_fam_budget_score(data)
    print("fam budget", family_budget_subscore)
    net_worth_subscore = net_worth_score(total_assets, total_debt)
    retirement_score = calculate_retirement_score(data)
    print(retirement_score)
   


    return jsonify({
        "incomeScore": income_subscore,
        "familyBudgetScore": family_budget_subscore,
        "netWorthScore": net_worth_subscore,
        "retirementScore": retirement_score,
        "receivedData": data
    })

@app.route('/')
def home():
    return "Backend is running!"


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
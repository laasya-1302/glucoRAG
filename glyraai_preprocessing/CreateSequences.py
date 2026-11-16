import pandas as pd
import numpy as np


# ============================================================
# FILES
# ============================================================

TRAIN_FILE = "Development_Train_SequenceReady.csv"
VALIDATION_FILE = "Development_Validation_SequenceReady.csv"

TRAIN_OUTPUT = "Development_Train_Sequences.npz"
VALIDATION_OUTPUT = "Development_Validation_Sequences.npz"


# ============================================================
# SETTINGS
# ============================================================

# 8 points × 15 minutes = 2 hours of history
INPUT_STEPS = 8

# Four future prediction horizons
TARGET_COLUMNS = [
    "Target_30",
    "Target_60",
    "Target_90",
    "Target_120"
]


# ============================================================
# INPUT FEATURES
# ============================================================

FEATURE_COLUMNS = [

    # Glucose
    "CGM",

    # Food
    "Carbs",
    "Carb_events",
    "Meal_Mass_g",
    "Meal_Event",

    # Insulin
    "Bolus_Insulin",
    "Basal_Insulin",

    # Other measurements
    "CBG",
    "Blood_Ketone",

    # --------------------------------------------------------
    # Time features
    # --------------------------------------------------------

    "Hour_sin",
    "Hour_cos",
    "Day_sin",
    "Day_cos",

    # --------------------------------------------------------
    # Dataset-level availability masks
    # --------------------------------------------------------

    "Has_CGM",
    "Has_Carbs",
    "Has_Bolus_Insulin",
    "Has_Basal_Insulin",
    "Has_CBG",
    "Has_Blood_Ketone",
    "Has_Meal_Mass",

    # --------------------------------------------------------
    # Row-level observation masks
    # --------------------------------------------------------

    "CGM_obs",
    "Carbs_obs",
    "Meal_Mass_g_obs",
    "Bolus_Insulin_obs",
    "Basal_Insulin_obs",
    "CBG_obs",
    "Blood_Ketone_obs"
]


# ============================================================
# CREATE SEQUENCES
# ============================================================

def create_sequences(input_file, output_file):

    print("=" * 70)
    print(f"Reading: {input_file}")
    print("=" * 70)

    # --------------------------------------------------------
    # Read data
    # --------------------------------------------------------

    df = pd.read_csv(input_file)

    print(f"Rows: {len(df):,}")

    # --------------------------------------------------------
    # Convert timestamp
    # --------------------------------------------------------

    df["Timestamp"] = pd.to_datetime(
        df["Timestamp"],
        format="mixed",
        errors="coerce"
    )

    # Remove invalid timestamps
    df = df.dropna(
        subset=["Timestamp"]
    ).reset_index(drop=True)

    # ========================================================
    # CREATE UNIQUE PATIENT KEY
    #
    # PtID can exist in both datasets.
    #
    # Therefore:
    #
    # Dataset + PtID
    #
    # is treated as the unique patient.
    # ========================================================

    df["PatientKey"] = (
        df["Dataset"].astype(str)
        + "_"
        + df["PtID"].astype(str)
    )

    print(
        f"Unique dataset-patients: "
        f"{df['PatientKey'].nunique():,}"
    )

    # ========================================================
    # SORT
    # ========================================================

    df = df.sort_values(
        ["PatientKey", "Timestamp"]
    ).reset_index(drop=True)

    # ========================================================
    # CREATE PREVIOUS TIMESTAMP
    # ========================================================

    df["PreviousTimestamp"] = (
        df.groupby("PatientKey")["Timestamp"]
        .shift(1)
    )

    # ========================================================
    # CALCULATE TIME DIFFERENCE
    # ========================================================

    df["DiffMinutes"] = (
        (
            df["Timestamp"]
            - df["PreviousTimestamp"]
        )
        .dt.total_seconds()
        / 60
    )

    # ========================================================
    # CHECK 15-MINUTE INTERVAL
    # ========================================================

    df["Is15Min"] = np.isclose(
        df["DiffMinutes"].fillna(-999),
        15.0,
        atol=0.1
    )

    # ========================================================
    # IDENTIFY GAPS
    #
    # A gap means the sequence cannot continue across it.
    # ========================================================

    df["Gap"] = (
        ~df["Is15Min"]
    ).astype(np.int32)

    # ========================================================
    # CREATE CONTINUOUS BLOCK
    # ========================================================

    df["Block"] = (
        df.groupby("PatientKey")["Gap"]
        .cumsum()
    )

    # ========================================================
    # UNIQUE BLOCK ID
    # ========================================================

    df["BlockKey"] = (
        df["PatientKey"]
        + "_"
        + df["Block"].astype(str)
    )

    # ========================================================
    # FIND BLOCKS WITH AT LEAST 8 TIMESTAMPS
    # ========================================================

    block_sizes = (
        df.groupby("BlockKey")
        .size()
    )

    valid_blocks = block_sizes[
        block_sizes >= INPUT_STEPS
    ].index

    df = df[
        df["BlockKey"].isin(valid_blocks)
    ].copy()

    # VERY IMPORTANT:
    # Reset the index after filtering.
    df = df.reset_index(drop=True)

    print(
        f"Continuous blocks >= 8 points: "
        f"{len(valid_blocks):,}"
    )

    # ========================================================
    # POSITION INSIDE EACH BLOCK
    # ========================================================

    df["BlockPosition"] = (
        df.groupby("BlockKey")
        .cumcount()
    )

    # ========================================================
    # CGM VALIDITY
    # ========================================================

    df["CGM_valid"] = (
        df["CGM_obs"] == 1
    ).astype(np.int8)

    # ========================================================
    # CHECK 8 CONSECUTIVE CGM VALUES
    # ========================================================

    df["CGM_8_count"] = (
        df.groupby("BlockKey")["CGM_valid"]
        .rolling(
            INPUT_STEPS,
            min_periods=INPUT_STEPS
        )
        .sum()
        .reset_index(
            level=0,
            drop=True
        )
    )

    # ========================================================
    # CANDIDATE ENDPOINTS
    # ========================================================

    candidate_mask = (
        df["BlockPosition"] >= INPUT_STEPS - 1
    )

    # Require all 8 historical CGM values
    candidate_mask = (
        candidate_mask
        & (
            df["CGM_8_count"]
            == INPUT_STEPS
        )
    )

    # ========================================================
    # REQUIRE ALL FOUR TARGETS
    # ========================================================

    candidate_mask = (
        candidate_mask
        & df[TARGET_COLUMNS]
        .notna()
        .all(axis=1)
    )

    # ========================================================
    # GET REAL NUMPY ROW POSITIONS
    #
    # This avoids the previous IndexError.
    # ========================================================

    candidate_positions = np.flatnonzero(
        candidate_mask.to_numpy()
    )

    print(
        f"Valid sequence endpoints: "
        f"{len(candidate_positions):,}"
    )

    # ========================================================
    # CONVERT FEATURES TO NUMPY
    # ========================================================

    feature_array = df[
        FEATURE_COLUMNS
    ].to_numpy(
        dtype=np.float32
    )

    # ========================================================
    # CONVERT TARGETS TO NUMPY
    # ========================================================

    target_array = df[
        TARGET_COLUMNS
    ].to_numpy(
        dtype=np.float32
    )

    # ========================================================
    # BUILD 8-STEP WINDOWS
    #
    # Example for endpoint t:
    #
    # t-105
    # t-90
    # t-75
    # t-60
    # t-45
    # t-30
    # t-15
    # t
    #
    # Each has 28 features.
    # ========================================================

    X_list = []

    for step in range(INPUT_STEPS):

        indices = (
            candidate_positions
            - (
                INPUT_STEPS
                - 1
                - step
            )
        )

        X_list.append(
            feature_array[indices]
        )

    # ========================================================
    # STACK INTO:
    #
    # (samples, 8, 28)
    # ========================================================

    X = np.stack(
        X_list,
        axis=1
    )

    # ========================================================
    # TARGETS
    #
    # (samples, 4)
    #
    # [30, 60, 90, 120]
    # ========================================================

    Y = target_array[
        candidate_positions
    ]

    # ========================================================
    # FINAL SAFETY CHECK
    # ========================================================

    valid = (
        np.isfinite(X).all(axis=(1, 2))
        &
        np.isfinite(Y).all(axis=1)
    )

    X = X[valid]
    Y = Y[valid]

    # ========================================================
    # RESULTS
    # ========================================================

    print("\n")
    print("=" * 70)
    print("SEQUENCE RESULTS")
    print("=" * 70)

    print(
        f"Valid sequences: {len(X):,}"
    )

    print(
        f"X shape: {X.shape}"
    )

    print(
        f"Y shape: {Y.shape}"
    )

    # ========================================================
    # EXPECTED STRUCTURE
    # ========================================================

    print("\nExpected structure:")

    print(
        "X = (number_of_sequences, 8, 28)"
    )

    print(
        "Y = (number_of_sequences, 4)"
    )

    # ========================================================
    # SAVE
    # ========================================================

    np.savez_compressed(
        output_file,
        X=X,
        Y=Y
    )

    print("\nSaved:")
    print(output_file)

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # TRAIN
    # --------------------------------------------------------

    create_sequences(
        TRAIN_FILE,
        TRAIN_OUTPUT
    )

    print("\n")

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    create_sequences(
        VALIDATION_FILE,
        VALIDATION_OUTPUT
    )
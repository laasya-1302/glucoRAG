import pandas as pd
import numpy as np


# ============================================================
# FILES
# ============================================================

TRAIN_FILE = "Development_Train_Normalized.csv"
VALIDATION_FILE = "Development_Validation_Normalized.csv"

TRAIN_OUTPUT = "Development_Train_SequenceReady.csv"
VALIDATION_OUTPUT = "Development_Validation_SequenceReady.csv"


# ============================================================
# FEATURES
# ============================================================

NUMERIC_FEATURES = [
    "CGM",
    "Carbs",
    "Carb_events",
    "Meal_Mass_g",
    "Meal_Event",
    "Bolus_Insulin",
    "Basal_Insulin",
    "CBG",
    "Blood_Ketone"
]

TIME_FEATURES = [
    "Hour_sin",
    "Hour_cos",
    "Day_sin",
    "Day_cos"
]

AVAILABILITY_MASKS = [
    "Has_CGM",
    "Has_Carbs",
    "Has_Bolus_Insulin",
    "Has_Basal_Insulin",
    "Has_CBG",
    "Has_Blood_Ketone",
    "Has_Meal_Mass"
]

TARGET_COLUMNS = [
    "Target_30",
    "Target_60",
    "Target_90",
    "Target_120"
]


# ============================================================
# FUNCTION
# ============================================================

def prepare_file(input_file, output_file):

    print("=" * 70)
    print(f"Reading: {input_file}")
    print("=" * 70)

    df = pd.read_csv(input_file)

    print(f"Rows: {len(df):,}")

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    df["Timestamp"] = pd.to_datetime(
        df["Timestamp"],
        format="mixed",
        errors="coerce"
    )

    # --------------------------------------------------------
    # Create ROW-LEVEL observation masks
    #
    # 1 = value was actually present
    # 0 = value was missing
    # --------------------------------------------------------

    observation_features = [
        "CGM",
        "Carbs",
        "Meal_Mass_g",
        "Bolus_Insulin",
        "Basal_Insulin",
        "CBG",
        "Blood_Ketone"
    ]

    for feature in observation_features:

        mask_name = feature + "_obs"

        df[mask_name] = (
            df[feature].notna()
            .astype(np.float32)
        )

    # --------------------------------------------------------
    # Missing numeric values
    #
    # IMPORTANT:
    # These values were already normalized using TRAINING
    # statistics.
    #
    # Therefore:
    #
    # NaN -> 0
    #
    # means "replace missing value with the training mean"
    # in standardized space.
    #
    # The observation mask tells the model that it was missing.
    # --------------------------------------------------------

    for feature in NUMERIC_FEATURES:

        if feature in df.columns:

            df[feature] = (
                df[feature]
                .fillna(0)
                .astype(np.float32)
            )

    # --------------------------------------------------------
    # Time features
    # --------------------------------------------------------

    for feature in TIME_FEATURES:

        df[feature] = (
            df[feature]
            .fillna(0)
            .astype(np.float32)
        )

    # --------------------------------------------------------
    # Availability masks
    # --------------------------------------------------------

    for feature in AVAILABILITY_MASKS:

        df[feature] = (
            df[feature]
            .fillna(0)
            .astype(np.float32)
        )

    # --------------------------------------------------------
    # Targets
    #
    # DO NOT fill target NaNs.
    #
    # A sequence without all four targets will be removed
    # during sequence creation.
    # --------------------------------------------------------

    # --------------------------------------------------------
    # Check remaining NaNs
    # --------------------------------------------------------

    print("\nRemaining NaN values:")

    important_columns = (
        NUMERIC_FEATURES
        + TIME_FEATURES
        + AVAILABILITY_MASKS
        + TARGET_COLUMNS
    )

    for column in important_columns:

        count = df[column].isna().sum()

        if count > 0:
            print(f"{column:25} {count:,}")

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    df.to_csv(
        output_file,
        index=False
    )

    print("\nSaved:")
    print(output_file)

    print("\nNew observation masks:")

    for feature in observation_features:
        print(f"  {feature}_obs")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    prepare_file(
        TRAIN_FILE,
        TRAIN_OUTPUT
    )

    print("\n")

    prepare_file(
        VALIDATION_FILE,
        VALIDATION_OUTPUT
    )
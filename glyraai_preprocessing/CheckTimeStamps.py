import pandas as pd
import os

files = {
    "CGM": r"C:\Users\divya\OneDrive\Desktop\Glyra\HDeviceCGM.csv",
    "Wizard": r"C:\Users\divya\OneDrive\Desktop\Glyra\HDeviceWizard.csv",
    "Bolus": r"C:\Users\divya\OneDrive\Desktop\Glyra\HDeviceBolus.csv",
    "Basal": r"C:\Users\divya\OneDrive\Desktop\Glyra\HDeviceBasal.csv"
}

for name, path in files.items():

    print("\n" + "=" * 50)
    print(name)
    print("=" * 50)

    df = pd.read_csv(path)

    print("Rows:", len(df))
    print("Patients:", df["PtID" if "PtID" in df.columns else "PtId"].nunique())

    print("\nDay range:")
    print(df["DeviceDtTmDaysFromEnroll"].min(),
          "to",
          df["DeviceDtTmDaysFromEnroll"].max())

    print("\nTime examples:")
    print(df["DeviceTm"].head(10).tolist())

    print("\nMissing values:")
    print(df[["DeviceDtTmDaysFromEnroll", "DeviceTm"]].isna().sum())

    print("\nColumns:")
    print(df.columns.tolist())
import pandas as pd

path = r"C:\Users\divya\OneDrive\Desktop\Glyra\HDeviceCGM.csv"

df = pd.read_csv(
    path,
    usecols=["PtID", "DeviceDtTmDaysFromEnroll", "DeviceTm", "GlucoseValue"]
)

df["time"] = pd.to_timedelta(df["DeviceTm"])
df["timestamp"] = (
    pd.to_timedelta(df["DeviceDtTmDaysFromEnroll"], unit="D")
    + df["time"]
)

df = df.sort_values(["PtID", "timestamp"])

df["diff_minutes"] = (
    df.groupby("PtID")["timestamp"]
      .diff()
      .dt.total_seconds() / 60
)

print("CGM interval distribution:")
print(df["diff_minutes"].value_counts().head(20))

print("\nMedian interval:")
print(df["diff_minutes"].median(), "minutes")

print("\nMost common intervals:")
print(df["diff_minutes"].value_counts().head(10))
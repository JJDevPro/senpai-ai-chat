"""
Referenz-Script: Lauf-CSV Analyse für den Overlord-Coach
Quelle: Apple Watch Ultra 3 via Health Auto Export
"""
import pandas as pd
import numpy as np

def analyze_run_csv(file_path):
    df = pd.read_csv(file_path, sep=';', decimal=',')
    df.columns = df.columns.str.strip()
    df['ISO8601'] = pd.to_datetime(df['ISO8601'])

    # KADENZ ×2 (CSV = Single-Foot!)
    if 'Cadence (count/min)' in df.columns:
        df['Cadence_spm'] = df['Cadence (count/min)'] * 2

    # Speed → Pace (min/km), Speed=0 filtern!
    if 'Speed (m/s)' in df.columns:
        df['Pace_min_km'] = np.where(df['Speed (m/s)'] > 0, (1000 / (df['Speed (m/s)'] * 60)), np.nan)

    def format_pace(pace_float):
        if pd.isna(pace_float) or pace_float == float('inf'):
            return "00:00"
        mins = int(pace_float)
        secs = int((pace_float - mins) * 60)
        return f"{mins}:{secs:02d}"

    # Segment-Analyse (Lap = manueller Split, z.B. Qualberg)
    laps_summary = []
    if 'Lap' in df.columns:
        for lap, group in df.groupby('Lap'):
            valid_speed = group[group['Speed (m/s)'] > 0]
            avg_speed = valid_speed['Speed (m/s)'].mean()

            # Distance ist KUMULATIV → Lap-Distanz = max - min
            lap_dist = group['Distance (meter)'].max() - group['Distance (meter)'].min()
            duration = (group['ISO8601'].max() - group['ISO8601'].min()).total_seconds()

            laps_summary.append({
                'Lap': lap,
                'Duration_sec': duration,
                'Distance_m': lap_dist,
                'Avg_HR': group['Heart Rate (bpm)'].mean(),
                'Max_HR': group['Heart Rate (bpm)'].max(),
                'Avg_Cadence': group['Cadence_spm'].mean(),
                'Avg_GCT': group['GCT (ms)'].mean(),
                'Avg_Pace': format_pace(1000 / (avg_speed * 60)) if avg_speed > 0 else "00:00",
                'Avg_Power': group['Power (watt)'].mean()
            })

    # Gesamt
    valid_speed_overall = df[df['Speed (m/s)'] > 0]
    total_dist = df['Distance (meter)'].max() - df['Distance (meter)'].min()
    total_duration = (df['ISO8601'].max() - df['ISO8601'].min()).total_seconds()
    overall_avg_speed = valid_speed_overall['Speed (m/s)'].mean()

    summary = {
        'Total_Distance_m': total_dist,
        'Total_Duration_sec': total_duration,
        'Avg_HR': df['Heart Rate (bpm)'].mean(),
        'Max_HR': df['Heart Rate (bpm)'].max(),
        'Avg_Cadence_spm': df['Cadence_spm'].mean(),
        'Avg_GCT_ms': df['GCT (ms)'].mean(),
        'Avg_Pace': format_pace(1000 / (overall_avg_speed * 60)) if overall_avg_speed > 0 else "00:00"
    }

    return pd.DataFrame(laps_summary), summary

if __name__ == '__main__':
    laps_df, summary = analyze_run_csv("Trainings/2026-02-28-090434-Laufen outdoor-Apple Watch Ultra 3.csv")
    print(laps_df.to_string())
    print(f"\n--- OVERALL ---")
    for k, v in summary.items():
        print(f"{k}: {v}")

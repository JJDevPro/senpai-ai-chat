"""
Referenz-Script: Krafttraining-CSV Analyse für den Overlord-Coach
Quelle: Apple Watch Ultra 3 via Health Auto Export
"""
import pandas as pd
import numpy as np

def analyze_gym_csv(file_path):
    df = pd.read_csv(file_path, sep=';', decimal=',')
    df.columns = df.columns.str.strip()
    df['ISO8601'] = pd.to_datetime(df['ISO8601'])

    laps_summary = []
    
    # Segment-Analyse (Lap = Gerätewechsel)
    if 'Lap' in df.columns and df['Lap'].notna().any():
        for lap, group in df.groupby('Lap'):
            duration = (group['ISO8601'].max() - group['ISO8601'].min()).total_seconds()
            laps_summary.append({
                'Lap': int(lap),
                'Duration_sec': duration,
                'Duration_formatted': f"{int(duration // 60)}m {int(duration % 60)}s",
                'Avg_HR': round(group['Heart Rate (bpm)'].mean(), 1),
                'Max_HR': group['Heart Rate (bpm)'].max()
            })
    else:
        # Fallback falls keine manuellen Laps gesetzt wurden
        pass

    # Gesamt-Zusammenfassung
    total_duration = (df['ISO8601'].max() - df['ISO8601'].min()).total_seconds()
    
    summary = {
        'Total_Duration_sec': total_duration,
        'Total_Duration_formatted': f"{int(total_duration // 60)}m {int(total_duration % 60)}s",
        'Overall_Avg_HR': round(df['Heart Rate (bpm)'].mean(), 1),
        'Overall_Max_HR': df['Heart Rate (bpm)'].max(),
        'Total_Laps_Count': len(laps_summary) if laps_summary else 1
    }

    return pd.DataFrame(laps_summary) if laps_summary else None, summary

if __name__ == '__main__':
    # Beispielaufruf
    print("Gym CSV Analyzer bereit. Übergib eine Funktionelles Krafttraining CSV.")

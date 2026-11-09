# -*- coding: utf-8 -*-
"""
OhioT1DM Dataset Preprocessing Script
Processes XML format data for short sequence model (30-min history -> 60-min prediction)

Sequence Configuration:
- Historical data length: 30 minutes (seq_len=6)
- Prediction length: 60 minutes (pred_len=12)  
- Label length: 10 minutes (label_len=2)

Usage:
python preprocess_ohio.py
"""

import os
import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
import pickle
from sklearn.preprocessing import StandardScaler
from datetime import datetime
import xml.etree.ElementTree as ET
import warnings
warnings.filterwarnings('ignore')

class CGMDatasetShort(Dataset):
    """Short sequence CGM dataset class"""
    def __init__(self, data, seq_len=6, pred_len=12, label_len=2):
        self.data = data
        self.seq_len = seq_len      # 30 minutes = 6 x 5-minute intervals
        self.pred_len = pred_len    # 60 minutes = 12 x 5-minute intervals  
        self.label_len = label_len  # 10 minutes = 2 x 5-minute intervals
        
    def __len__(self):
        return len(self.data) - self.seq_len - self.pred_len + 1
    
    def __getitem__(self, idx):
        # Input sequence (seq_len, features)
        s_begin = idx
        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = r_begin + self.label_len + self.pred_len
        
        seq_x = self.data[s_begin:s_end]
        seq_y = self.data[r_begin:r_end]
        
        # Time feature marks (using cyc frequency, requires 2D features)
        seq_x_mark = np.zeros((self.seq_len, 2))  # Sine and cosine features
        seq_y_mark = np.zeros((self.label_len + self.pred_len, 2))
        
        return torch.FloatTensor(seq_x), torch.FloatTensor(seq_y), \
               torch.FloatTensor(seq_x_mark), torch.FloatTensor(seq_y_mark)

def parse_ohio_xml(xml_file, default_year=None):
    """Parse OhioT1DM XML file and extract CGM data"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        patient_id = root.get('id')
        
        # Extract glucose readings
        glucose_data = []
        for event in root.find('glucose_level').findall('event'):
            timestamp = event.get('ts')
            value = event.get('value')
            
            if timestamp and value:
                dt = None
                for fmt in ('%m-%d-%Y %H:%M:%S', '%d-%m-%Y %H:%M:%S'):
                    try:
                        dt = pd.to_datetime(timestamp, format=fmt)
                        break
                    except ValueError:
                        continue
                if dt is None:
                    continue
                if default_year is not None:
                    try:
                        year_int = int(default_year)
                        dt = dt.replace(year=year_int)
                    except Exception:
                        pass
                try:
                    glucose_value = float(value)
                except ValueError:
                    continue
                glucose_data.append({
                    'DateTime': dt,
                    'GlucoseValue': glucose_value,
                    'PtID': patient_id
                })

        return pd.DataFrame(glucose_data)
    
    except Exception as e:
        print(f"Error parsing {xml_file}: {e}")
        return None

def load_ohio_data(data_path, split='train', years=['2018', '2020']):
    """Load OhioT1DM dataset from XML files"""
    print(f"Loading OhioT1DM {split} data from years: {years}...")
    
    all_data = []
    patient_count = 0
    
    for year in years:
        split_path = os.path.join(data_path, year, split)
        
        if not os.path.exists(split_path):
            print(f"Warning: Path does not exist: {split_path}")
            continue
        
        # Get all XML files
        xml_files = [f for f in os.listdir(split_path) if f.endswith('.xml')]
        print(f"Found {len(xml_files)} XML files in {year}/{split}")
        
        for xml_file in xml_files:
            xml_path = os.path.join(split_path, xml_file)
            df = parse_ohio_xml(xml_path, default_year=year)
            
            if df is not None and len(df) > 0:
                all_data.append(df)
                patient_count += 1
                print(f"  Loaded patient {df['PtID'].iloc[0]}: {len(df)} data points")
    
    if not all_data:
        print("Error: No data loaded!")
        return None
    
    # Combine all data
    combined_data = pd.concat(all_data, ignore_index=True)
    print(f"\nTotal patients loaded: {patient_count}")
    print(f"Total data points: {len(combined_data)}")
    
    return combined_data

def create_patient_sequences_short(data, min_sequence_length=50):
    """Create time series for each patient - optimized for short sequences
    
    Args:
        min_sequence_length: Minimum sequence length, adjusted to 50 for short sequences
                           (seq_len=6 + pred_len=12 + buffer=32)
    """
    print("Creating short time series for each patient...")
    
    patient_sequences = {}
    
    for patient_id in data['PtID'].unique():
        patient_data = data[data['PtID'] == patient_id].copy()
        patient_data = patient_data.sort_values('DateTime')
        
        # Remove duplicates if any
        patient_data = patient_data.drop_duplicates(subset=['DateTime'])
        
        # Only keep the original readings without heavy interpolation
        # This preserves the natural variability of the data
        glucose_values = patient_data['GlucoseValue'].values
        
        # For short sequences, accept shorter patient data
        if len(glucose_values) >= min_sequence_length:
            patient_sequences[patient_id] = glucose_values.reshape(-1, 1)
            print(f"  Patient {patient_id}: {len(glucose_values)} data points")
            
    print(f"Valid patients: {len(patient_sequences)}")
    print(f"Minimum sequence length requirement: {min_sequence_length} data points")
    return patient_sequences

def create_domain_datasets_short(patient_sequences, patient_list, seq_len=6, pred_len=12):
    """Create short sequence domain datasets (each patient as a domain)"""
    datasets = []
    
    for patient_id in patient_list:
        if patient_id in patient_sequences:
            patient_data = patient_sequences[patient_id]
            # Ensure patient data is long enough to create at least one sequence
            if len(patient_data) >= seq_len + pred_len:
                dataset = CGMDatasetShort(patient_data, seq_len, pred_len)
                if len(dataset) > 0:
                    datasets.append(dataset)
                    print(f"  Patient {patient_id}: {len(patient_data)} data points -> {len(dataset)} sequences")
    
    print(f"Created {len(datasets)} patient domain datasets")
    return datasets

def collate_fn(batch):
    """Global collate function to avoid serialization issues"""
    batch_x, batch_y, batch_x_mark, batch_y_mark = zip(*batch)
    return torch.stack(batch_x), torch.stack(batch_y), \
           torch.stack(batch_x_mark), torch.stack(batch_y_mark)

def create_combined_dataloader(datasets, batch_size=32, shuffle=True):
    """Create combined dataloader (for MLDG)"""
    if not datasets:
        return None
    
    # Combine all datasets
    all_data = []
    for dataset in datasets:
        for i in range(len(dataset)):
            all_data.append(dataset[i])
    
    if not all_data:
        return None
    
    print(f"Total sequences: {len(all_data)}")
    return DataLoader(all_data, batch_size=batch_size, shuffle=shuffle, collate_fn=collate_fn)

def main():
    """Main function"""
    # Data path
    data_path = "OhioT1DM"
    output_path = "data_loader_ohio"
    
    # Create output directory
    os.makedirs(output_path, exist_ok=True)
    
    # Set random seed
    np.random.seed(42)
    torch.manual_seed(42)
    
    print("[INFO] Starting OhioT1DM data preprocessing...")
    print("[INFO] Configuration: 30-min history -> 60-min prediction")
    
    # Load training data (from both 2018 and 2020)
    train_data = load_ohio_data(data_path, split='train', years=['2018', '2020'])
    
    # Load testing data (from both 2018 and 2020)
    test_data = load_ohio_data(data_path, split='test', years=['2018', '2020'])
    
    if train_data is None or test_data is None:
        print("Error: Failed to load data")
        return
    
    # Combine all data for standardization
    all_data = pd.concat([train_data, test_data], ignore_index=True)
    
    # Create patient sequences
    print("\n[INFO] Processing training data...")
    train_patient_sequences = create_patient_sequences_short(train_data, min_sequence_length=50)
    
    print("\n[INFO] Processing testing data...")
    test_patient_sequences = create_patient_sequences_short(test_data, min_sequence_length=50)
    
    if not train_patient_sequences and not test_patient_sequences:
        print("Error: No valid patient data found")
        return
    
    # Data standardization - fit on training data only
    print("\n[INFO] Performing data standardization...")
    train_values = np.concatenate([seq for seq in train_patient_sequences.values()])
    scaler = StandardScaler()
    scaler.fit(train_values)
    
    print(f"Scaler parameters: mean={scaler.mean_[0]:.2f}, std={scaler.scale_[0]:.2f}")
    
    # Standardize each patient's data
    for patient_id in train_patient_sequences:
        train_patient_sequences[patient_id] = scaler.transform(train_patient_sequences[patient_id])
    
    for patient_id in test_patient_sequences:
        test_patient_sequences[patient_id] = scaler.transform(test_patient_sequences[patient_id])
    
    # Save standardization scaler
    with open(os.path.join(output_path, "ohio_scaler.pkl"), "wb") as f:
        pickle.dump(scaler, f)
    print("[SUCCESS] Saved OhioT1DM data scaler")
    
    # Create datasets
    train_patient_list = list(train_patient_sequences.keys())
    test_patient_list = list(test_patient_sequences.keys())
    
    print(f"\n[INFO] Creating training datasets...")
    train_datasets = create_domain_datasets_short(train_patient_sequences, train_patient_list)
    
    print(f"\n[INFO] Creating testing datasets...")
    test_datasets = create_domain_datasets_short(test_patient_sequences, test_patient_list)
    
    # Create dataloaders
    if train_datasets:
        train_loader = create_combined_dataloader(train_datasets, batch_size=256, shuffle=True)
        torch.save(train_loader, os.path.join(output_path, "ohio_train_loader.pth"))
        print("[SUCCESS] Saved training dataloader")
    else:
        print("[WARNING] No training datasets created")
    
    if test_datasets:
        test_loader = create_combined_dataloader(test_datasets, batch_size=256, shuffle=False)
        torch.save(test_loader, os.path.join(output_path, "ohio_test_loader.pth"))
        print("[SUCCESS] Saved testing dataloader")
    else:
        print("[WARNING] No testing datasets created")
    
    print("\n[SUCCESS] OhioT1DM data preprocessing completed!")
    print(f"[INFO] Data files saved to: {output_path}/")
    
    # Output statistics
    print("\n[STATS] Data Statistics:")
    if train_datasets:
        total_train_sequences = sum(len(ds) for ds in train_datasets)
        print(f"   Training sequences: {total_train_sequences}")
        print(f"   Training patients: {len(train_datasets)}")
    if test_datasets:
        total_test_sequences = sum(len(ds) for ds in test_datasets)
        print(f"   Testing sequences: {total_test_sequences}")
        print(f"   Testing patients: {len(test_datasets)}")
    print(f"   Sequence configuration: History {6*5}min -> Prediction {12*5}min")

if __name__ == "__main__":
    main()

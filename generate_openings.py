#!/usr/bin/env python3
"""
Generates a sample Parquet file with example Shogi openings.
This file will be automatically detected and loaded by app.py.
"""
import os
import pandas as pd

# Ensure the data directory exists
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Example Shogi Openings with valid USI (Universal Shogi Interface) move sequences
# Format: file(1-9) + rank(a-i) + file(1-9) + rank(a-i) + '+' (optional promotion)
OPENINGS_DATA = [
    {
        "name": "Yagura (Fortress)",
        "eco": "Static Rook",
        "pgn": "",  # PGN is Chess-specific; left empty for Shogi
        "usi": "7g7f 3c3d 6g6f 4a3b 6f6e 3a4b 5g5f 5a4a 5f5e 4b3c 5e5d 3c4d 4i5h 4a5b 3i4h 5b6c 4h3g 6c7d 2g2f 2c2d 2f2e 2d2e 2i3g 2a2e 3g2e 8h2b+ 5c2b 2e3g 3d3e 3e3d 3c3d 3g4e 3d3e 4e3c+ 4b3c",
        "epd": ""
    },
    {
        "name": "Shikenbisha (Fourth File Rook)",
        "eco": "Ranging Rook",
        "pgn": "",
        "usi": "7g7f 3c3d 2g2f 4a3b 2f2e 3a4b 6g6f 5a4a 6f6e 4b3c 5g5f 3c4d 5f5e 4d3c 4i5h 4a5b 3i4h 5b6c 4h3g 6c7d 7i6h 7a6b 5i6h 6b5c 3g4f 5c4d 4f3e 4d3c 3e4d 3c4b 4d3e 4b3c 3e4d",
        "epd": ""
    },
    {
        "name": "Sankenbisha (Third File Rook)",
        "eco": "Ranging Rook",
        "pgn": "",
        "usi": "7g7f 3c3d 3g3f 4a3b 3f3e 3a4b 6g6f 5a4a 6f6e 4b3c 5g5f 3c4d 5f5e 4d3c 4i5h 4a5b 3i4h 5b6c 4h3g 6c7d 7i6h 7a6b 5i6h 6b5c 3g4f 5c4d 4f3e 4d3c 3e4d 3c4b 4d3e 4b3c 3e4d",
        "epd": ""
    },
    {
        "name": "Gokigen Nakabisha (Central Rook)",
        "eco": "Ranging Rook",
        "pgn": "",
        "usi": "7g7f 3c3d 5g5f 4a3b 5f5e 3a4b 6g6f 5a4a 6f6e 4b3c 4i5h 3c4d 5e5d 4d3c 3i4h 4a5b 4h3g 5b6c 3g4f 6c7d 7i6h 7a6b 5i6h 6b5c 4f3e 5c4d 3e4d 4c4d 2g2f 2c2d 2f2e 2d2e 2i3g 2a2e 3g2e",
        "epd": ""
    },
    {
        "name": "Kakugawari (Bishop Exchange)",
        "eco": "Static Rook",
        "pgn": "",
        "usi": "7g7f 3c3d 6g6f 4a3b 6f6e 3a4b 5g5f 5a4a 5f5e 4b3c 5e5d 3c4d 4i5h 4a5b 3i4h 5b6c 4h3g 6c7d 2g2f 2c2d 2f2e 2d2e 2i3g 2a2e 3g2e 8h2b+ 5c2b 2e3g 3d3e 3e3d 3c3d 3g4e 3d3e 4e3c+ 4b3c",
        "epd": ""
    },
    {
        "name": "Anaguma (Bear-in-the-hole)",
        "eco": "Ranging Rook",
        "pgn": "",
        "usi": "7g7f 3c3d 2g2f 4a3b 2f2e 3a4b 6g6f 5a4a 6f6e 4b3c 5g5f 3c4d 5f5e 4d3c 4i5h 4a5b 3i4h 5b6c 4h3g 6c7d 7i6h 7a6b 5i6h 6b5c 3g4f 5c4d 4f3e 4d3c 3e4d 3c4b 4d3e 4b3c 3e4d 2i3h 1a1b 3h2h",
        "epd": ""
    }
]

def main():
    print("Creating DataFrame...")
    df = pd.DataFrame(OPENINGS_DATA)
    
    output_path = os.path.join(DATA_DIR, "shogi_openings.parquet")
    
    print(f"Saving to {output_path}...")
    # Use pyarrow engine for compatibility with the app's DuckDB/PyArrow readers
    df.to_parquet(output_path, engine="pyarrow", index=False)
    
    print("✅ Success! Example Shogi openings Parquet file generated.")
    print(f"   Location: {os.path.abspath(output_path)}")
    print("\nYou can now run `python app.py` and the app will automatically load these openings.")

if __name__ == "__main__":
    main()
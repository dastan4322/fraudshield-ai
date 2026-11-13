"""Generate explicitly synthetic records locally, never real financial data."""
import argparse
from app.ml import synthetic
parser = argparse.ArgumentParser()
parser.add_argument("output",help="Output CSV path; generated CSV is gitignored")
args=parser.parse_args()
synthetic().to_csv(args.output,index=False)
print("Generated synthetic data. Not real transactions and not Kaggle.")

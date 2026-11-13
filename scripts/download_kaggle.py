"""Use Kaggle's supported CLI with user-managed credentials; never download during tests."""
import argparse
import subprocess
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument("--output",default="data/kaggle")
args=parser.parse_args()
path=Path(args.output);path.mkdir(parents=True,exist_ok=True)
subprocess.run(["kaggle","datasets","download","-d","mlg-ulb/creditcardfraud","-p",str(path),"--unzip"],check=True)
if not (path/"creditcard.csv").is_file():
    raise RuntimeError("Kaggle command did not produce creditcard.csv.")
print("Downloaded local dataset. Review Kaggle terms; do not commit data.")

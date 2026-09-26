#!/usr/bin/env python3
"""Dry-run by default; apply requires an exact plan and a fresh verified backup."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app.db.integrity_repair import read_plan, apply_repair


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--output', type=Path, help='Write the dry-run plan (no content/secrets)')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    if args.apply and (not args.plan or not args.backup):
        parser.error('--apply requires --plan and --backup')
    if args.database is None:
        from local_data import current_paths
        args.database = current_paths()[0]
    result = (apply_repair(args.database, json.loads(args.plan.read_text()), args.backup)
              if args.apply else read_plan(args.database))
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text)

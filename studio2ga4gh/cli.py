"""Command-line interface for studio2ga4gh."""
from __future__ import annotations
import argparse, sys
from .converter import convert_file

def main(argv=None):
    parser = argparse.ArgumentParser(prog="studio2ga4gh",
        description="Convert Pedigree Studio session JSON to GA4GH Pedigree and Phenopackets.")
    parser.add_argument("input", help="Path to the Pedigree Studio session .json file")
    parser.add_argument("-o", "--output-prefix", default=None, dest="output_prefix",
        help="Base name for output files (default: input filename stem)")
    parser.add_argument("-d", "--output-dir", default=None, dest="output_dir",
        help="Directory for output files (default: same as input)")
    parser.add_argument("--phenotypes", action="store_true",
        help="Record conditions as phenotypicFeatures (HPO-style) instead of diseases in Phenopackets output")
    parser.add_argument("--include-names", action="store_true", dest="include_names",
        help="Include names and dates of birth in the output (default: anonymous)")
    args = parser.parse_args(argv)
    try:
        result = convert_file(args.input, output_prefix=args.output_prefix,
                             output_dir=args.output_dir,
                             use_phenotypic_features=args.phenotypes,
                             include_names=args.include_names)
        print(result.summary)
        for filepath, _ in result.files:
            print(f"  Written: {filepath}")
        return 0
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr); return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr); return 1

if __name__ == "__main__":
    sys.exit(main())

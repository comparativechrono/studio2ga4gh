"""Allow running as `python -m studio2ga4gh`."""
import sys
from .cli import main
sys.exit(main())

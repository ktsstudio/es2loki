import sys

from es2loki.commands.transfer import BaseTransfer, run_transfer

if __name__ == "__main__":
    sys.exit(run_transfer(BaseTransfer()))

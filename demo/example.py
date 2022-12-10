import sys
from typing import MutableMapping, Optional

from es2loki import BaseTransfer, run_transfer


class Transfer(BaseTransfer):
    def extract_doc_labels(self, source: dict) -> Optional[MutableMapping[str, str]]:
        return dict(
            app=source.get("fields", {}).get("service_name"),
            job="logs",
            level=source.get("level"),
            node_name=source.get("host", {}).get("name"),
            logger_name=source.get("logger_name"),
        )


if __name__ == "__main__":
    sys.exit(run_transfer(Transfer()))

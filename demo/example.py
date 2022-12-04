import re
import sys
from typing import MutableMapping, Optional

from es2loki import BaseTransfer, run_transfer

http_request_re = re.compile(
    r".*(POST|GET|OPTIONS|PUT|DELETE|HEAD|CONNECT|TRACE|PATCH) .+ HTTP/1\..*"
)
invalid_char_re = re.compile(r"(\W+)")
invalid_char_domain_re = re.compile(r"[^\w.\-_]")


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

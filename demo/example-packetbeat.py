import re
import sys
from typing import MutableMapping, Optional

from es2loki import BaseTransfer, run_transfer

http_request_re = re.compile(
    r".*(POST|GET|OPTIONS|PUT|DELETE|HEAD|CONNECT|TRACE|PATCH) .+ HTTP/1\..*"
)
invalid_char_re = re.compile(r"(\W+)")
invalid_char_domain_re = re.compile(r"[^\w.\-_]")


class TransferPacketbeat(BaseTransfer):
    def make_es_sort(self) -> list:
        sort = super().make_es_sort()
        return [sort[0]]  # sort only by timestamp

    def make_es_search_after(self) -> Optional[list]:
        pos = self.latest_positions

        if not pos or pos.iszero:
            return None

        return [
            pos.timestamp,
        ]

    def extract_doc_labels(self, source: dict) -> Optional[MutableMapping[str, str]]:
        method = "null"

        if request := source.get("request"):
            if m := http_request_re.match(request):
                method = m.group(1)
                invalid_char_re.sub("", method)

        domain = source.get("server", {}).get("domain")
        if domain:
            if invalid_char_domain_re.search(domain) is not None:
                return None

        network = source.get("network", {})

        return dict(
            env=source.get("env"),
            job="packetbeat",
            node_name=source.get("host", {}).get("name"),
            http_method=method,
            http_status=source.get("http", {}).get("response", {}).get("status_code"),
            domain=domain,
            status=source.get("status"),
            network_type=network.get("type"),
            network_direction=network.get("direction"),
            network_protoctol=network.get("protoctol"),
            network_transport=network.get("transport"),
        )


if __name__ == "__main__":
    sys.exit(run_transfer(TransferPacketbeat()))

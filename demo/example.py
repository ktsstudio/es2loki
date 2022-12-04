import re
import sys
from typing import MutableMapping, Optional

from es2loki.commands.transfer import BaseTransferLogs, run_transfer

http_request_re = re.compile(
    r".*(POST|GET|OPTIONS|PUT|DELETE|HEAD|CONNECT|TRACE|PATCH) .+ HTTP/1\..*"
)
invalid_char_re = re.compile(r"(\W+)")
invalid_char_domain_re = re.compile(r"[^\w.\-_]")


class TransferLogs(BaseTransferLogs):
    def __init__(self):
        super().__init__()
        self._is_packetbeat = "packetbeat" in self.es_index

    def make_es_sort(self) -> list:
        sort = super().make_es_sort()

        if not self._is_packetbeat:
            return sort

        return [sort[0]]  # sort only by timestamp

    def make_es_search_after(self) -> Optional[list]:
        pos = self.latest_positions

        if not pos or pos.iszero:
            return None

        if self._is_packetbeat:
            return [
                pos.timestamp,
            ]

        return [
            pos.timestamp,
            pos.log_offset,
        ]

    def extract_doc_labels(self, source: dict) -> Optional[MutableMapping[str, str]]:
        if self._is_packetbeat:
            return self._extract_labels_packetbeat(source)

        return self._extract_labels_filebeat(source)

    @staticmethod
    def _extract_labels_filebeat(source: dict) -> Optional[MutableMapping[str, str]]:
        return dict(
            app=source.get("fields", {}).get("service_name"),
            job="omni_services",
            level=source.get("level"),
            node_name=source.get("host", {}).get("name"),
            logger_name=source.get("logger_name"),
        )

    @staticmethod
    def _extract_labels_packetbeat(source: dict) -> Optional[MutableMapping[str, str]]:
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
    sys.exit(run_transfer(TransferLogs()))

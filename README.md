# es2loki

[![Build](https://github.com/ktsstudio/es2loki/actions/workflows/package.yml/badge.svg?branch=main)](https://github.com/ktsstudio/es2loki/actions)
[![Build](https://github.com/ktsstudio/es2loki/actions/workflows/docker.yml/badge.svg?branch=main)](https://github.com/ktsstudio/es2loki/actions)
[![PyPI](https://img.shields.io/pypi/v/es2loki.svg)](https://pypi.python.org/pypi/es2loki)
[![Docker Image](https://img.shields.io/docker/v/ktshub/es2loki?label=docker&sort=semver)](https://hub.docker.com/repository/docker/ktshub/es2loki)

`es2loki` is a migration library that helps to transfer logs from
Elasticsearch to Grafana Loki.

To use es2loki currently you need to define your own mapping of elasticsearch documents
to labels for Grafana Loki.

## Demo
You may find helpful a [demo](demo) folder which contains a fully-sufficient demo stand
that demonstrates transferring logs using `es2loki`.

## Usage
In the simplest form you don't need to write any Python code at all,
Loki will receive no meaningful labels, but nevertheless - let's see how it works.

```bash
$ pip install -U es2loki
$ ELASTIC_HOSTS=http://localhost:9200 \
  ELASTIC_INDEX="filebeat-*" \
  LOKI_URL=http://localhost:3100 \
  python -m es2loki
```

In order to override default `es2loki` behaviour you need to subclass
a `es2loki.BaseTransfer` class.

To declare how documents map to Loki labels you have to override a
`extract_doc_labels` method (see [demo/example.py](demo/example.py)):

```python

from es2loki import BaseTransfer


class TransferLogs(BaseTransfer):
    def extract_doc_labels(self, source: dict) -> Optional[MutableMapping[str, str]]:
        return dict(
            app=source.get("fields", {}).get("service_name"),
            job="logs",
            level=source.get("level"),
            node_name=source.get("host", {}).get("name"),
            logger_name=source.get("logger_name"),
        )
```

You can run this using the following code:
```python
import sys
from es2loki import run_transfer

if __name__ == "__main__":
    sys.exit(run_transfer(TransferLogs()))
```

You can find more examples in the [demo](demo) folder.

### Sorting

By default `es2loki` assumes that in the documents returned from Elasticsearch
there are fields `@timestamp` (you can change the name - see below) and `log.offset`.
Using these 2 fields we can be sure that we will not reread the same lines multiple times.
But if you have your fields that could guarantee such a behaviour - please
override a `make_es_sort` and `make_es_search_after` methods.

* `make_es_sort` defines by which fields the sorting will happen.
* `make_es_search_after` defines an initial "offset". It is needed to resume es2loki after a shutdown.

## Configuration

| name                    | default                            | description                                                        |
|-------------------------|------------------------------------|--------------------------------------------------------------------|
| ELASTIC_HOSTS           | http://localhost:9200              | Elasticsearch hosts. Separate multiple hosts using `,`             |
| ELASTIC_USER            | ""                                 | Elasticsearch username                                             |
| ELASTIC_PASSWORD        | ""                                 | Elasticsearch password                                             |
| ELASTIC_INDEX           | ""                                 | Elasticsearch index pattern to search documents in                 |
| ELASTIC_BATCH_SIZE      | 3000                               | How much documents to extract from ES in one batch                 |
| ELASTIC_TIMEOUT         | 120                                | Elasticsearch `search` query timeout                               |
| ELASTIC_MAX_DATE        |                                    | Upper date limit (format is the same as @timestamp field)          |
| ELASTIC_TIMESTAMP_FIELD | @timestamp                         | Name of timesteamp field in Elasticsearch                          |
| LOKI_URL                | http://localhost:3100              | Loki instance URL                                                  |
| LOKI_USERNAME           | ""                                 | Loki username                                                      |
| LOKI_PASSWORD           | ""                                 | Loki password                                                      |
| LOKI_TENANT_ID          | ""                                 | Loki Tenant ID (Org ID)                                            |
| LOKI_BATCH_SIZE         | 1048576                            | Maximum batch size (in bytes)                                      |
| LOKI_POOL_LOAD_FACTOR   | 10                                 | Maximum number of push non-waiting requests                        |
| LOKI_PUSH_MODE          | pb                                 | `pb` - protobuf + snappy, `gzip` - json + gzip, `json` - just json |
| LOKI_WAIT_TIMEOUT       | 0                                  | How much time (in seconds) to wait after a Loki push request       |
| STATE_MODE              | db                                 | Configures es2loki persistence (`db` is recommended).              |
| STATE_START_OVER        |                                    | Clean up persisted data and start over                             |
| STATE_FILE_DIR          | /var/es2loki                       | `file` persistence location                                        |
| STATE_DB_URL            | postgres://127.0.0.1:5432/postgres | Database URL for `db` persistence                                  |




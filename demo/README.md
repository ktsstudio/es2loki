# es2loki demo

This folder demonstrates how you can use `es2loki` to transfer logs from
Elasticsearch to Loki.

The included `docker-compose.yml` populates Elasticsearch with some "old" logs
that needs to be transferred and some "new" logs that are already reside in
Loki and we `es2loki` must not interfere with them.

## Components

1. Elasticsearch
2. Kibana
3. filebeat (imports _"old"_ logs to Elasticsearch)
4. Grafana (login: admin/admin)
5. Loki
6. Promtail (imports _"new"_ logs to Loki)
7. PostgreSQL (needed for es2loki)
8. es2loki

## Usage

In order to run a demo you may use:
```bash
docker compose up
```

Once you run it, all the components will spin up and after **180 seconds** es2loki
will transfer logs from Elasticsearch to Loki. You can validate that by
accessing Grafana Explore and issue a following query for the December 3rd, 2022:
```
{job="logs"}
```
Or click the following [link](http://localhost:3000/explore?orgId=1&left=%7B%22datasource%22:%22P8E80F9AEF21F6940%22,%22queries%22:%5B%7B%22refId%22:%22A%22,%22datasource%22:%7B%22type%22:%22loki%22,%22uid%22:%22P8E80F9AEF21F6940%22%7D,%22editorMode%22:%22code%22,%22expr%22:%22%7Bjob%3D%5C%22logs%5C%22%7D%22,%22queryType%22:%22range%22%7D%5D,%22range%22:%7B%22from%22:%221670011200000%22,%22to%22:%221670097599000%22%7D%7D).

## How it works

`example.py` is where magic happens. Elasticsearch sorting and filtering
are specified there as well as mapping of documents to Loki labels.

You may also take a look at `example-packetbeat.py` to understand how
to tweak the transfer even more.

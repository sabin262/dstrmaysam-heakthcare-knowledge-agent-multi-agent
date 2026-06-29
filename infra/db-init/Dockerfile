FROM postgres:16-alpine

WORKDIR /db-init

COPY database/init/01_schema.sql ./01_schema.sql
COPY database/init/02_seed.sql ./02_seed.sql
COPY infra/db-init/run-db-init.sh ./run-db-init.sh

RUN chmod +x ./run-db-init.sh

ENTRYPOINT ["./run-db-init.sh"]

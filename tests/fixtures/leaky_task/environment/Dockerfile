FROM debian:bookworm-slim
WORKDIR /app
RUN seq 1 100 > /app/numbers.txt
COPY solve.sh expected_answer.txt /app/

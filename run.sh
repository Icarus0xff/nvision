#!/usr/bin/env sh

#!/bin/bash

for i in $(seq 1 1000); do
    echo "Running $i/1000"
    python wechat_moments.py \
        -t "AI🤖 基于视觉的软件操作测试,压力测试中-$i/1000" \
        -d 2
done

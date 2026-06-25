# Session Handoff: 周线选股改版

**Date:** 2026-06-25 **Project:** quant-stock-pro

## Current State
周线选股改版完成，已部署到服务器并push到GitHub。

## What We Did
4条件（堆量+均线多头+突破回踩）改为2条件（月线抬头+20日唯一涨停板），Tab改为手动触发扫描。

## Code Changes
- weekly_scanner.py -- 新增daily K线获取、涨停板检测，替换选股逻辑
- server.py:807 -- 新增 POST /api/scan/weekly-picks 端点
- static/index.html -- 加按钮、改字段、去自动加载

## Bugs Fixed
1. SCP首次静默失败，3个文件都没上传成功
2. Permission denied -- chown -R ubuntu:ubuntu 修复
3. api()不支持POST -- 改用fetch()直接发POST

## Next Steps
1. 观察量比扫描和周线选股表现，必要时调阈值
2. 多余文件被git追踪：.bak和.docx，考虑.gitignore
